import SwiftUI

// MARK: - Constants

private let INPUT_SIZE     = 25
private let HIDDEN_SIZE    = 24
private let N_SIGNALS      = 8
private let N_DRIVES       = 5
private let N_PERCEPTION   = 8
private let N_RELATIONSHIP = 4
private let RECURRENT_SIZE = 8
private let N_CONTEXT      = 12   // N_DRIVES + N_CONTEXT + N_RELATIONSHIP + RECURRENT_SIZE = 25

private let SIGNAL_NAMES = ["directness", "vulnerability", "playfulness", "initiative",
                            "depth", "warmth", "defiance", "curiosity"]

private let SIGNAL_SEMANTICS: [(String, String)] = [
    ("委婉","直说"), ("防御","袒露"), ("认真","玩闹"), ("被动","主动"),
    ("闲聊","深度"), ("冷淡","热情"), ("顺从","反抗"), ("无所谓","追问"),
]

private let SIGNAL_COLORS: [Color] = [
    Color(red:0.42,green:0.62,blue:0.75),
    Color(red:0.61,green:0.50,blue:0.80),
    Color(red:0.80,green:0.42,blue:0.53),
    Color(red:0.35,green:0.62,blue:0.47),
    Color(red:0.35,green:0.67,blue:0.75),
    Color(red:0.78,green:0.53,blue:0.29),
    Color(red:0.75,green:0.34,blue:0.34),
    Color(red:0.78,green:0.63,blue:0.19),
]

private let INPUT_GROUP_COLORS: [Color] = [
    Color(red:0.79,green:0.53,blue:0.24),
    Color(red:0.72,green:0.47,blue:0.47),
    Color(red:0.48,green:0.67,blue:0.53),
    Color(red:0.61,green:0.50,blue:0.72),
]

private let BRASS = Color(red:0.72,green:0.55,blue:0.20)
private let INK   = Color(red:0.24,green:0.14,blue:0.09)

// MARK: - Particle Definition
// All particle positions are derived from wall-clock time — zero mutable state in Canvas.

private struct ParticleDef {
    let x1,y1,cp1x,cp1y,cp2x,cp2y,x2,y2: CGFloat
    let color: Color
    let size: CGFloat
    let speed: Double   // loop traversals/second (idle only; 0 for fwd particles)
    let phase: Double   // initial phase (negative = delayed start for fwd particles)

    func position(t: Double) -> CGPoint {
        let t = max(0,min(1,t)), m = 1-t
        return CGPoint(
            x: CGFloat(m*m*m)*x1 + CGFloat(3*m*m*t)*cp1x + CGFloat(3*m*t*t)*cp2x + CGFloat(t*t*t)*x2,
            y: CGFloat(m*m*m)*y1 + CGFloat(3*m*m*t)*cp1y + CGFloat(3*m*t*t)*cp2y + CGFloat(t*t*t)*y2
        )
    }
}

// MARK: - NeuralNetworkView

struct NeuralNetworkView: View {
    @ObservedObject var debugState: EngineDebugState

    @State private var idleDefs: [ParticleDef] = []
    @State private var fwdW1:    [ParticleDef] = []
    @State private var fwdW2:    [ParticleDef] = []

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1.0/30.0)) { tl in
            Canvas { ctx, size in
                guard size.width > 10, size.height > 10 else { return }

                let now   = tl.date.timeIntervalSinceReferenceDate
                let nodes = computeNodePositions(size: size)
                guard !nodes.input.isEmpty, !nodes.hidden.isEmpty, !nodes.output.isEmpty else { return }

                // ── animPulse: wall-clock elapsed / duration ─────────────────
                // withAnimation cannot drive Canvas — we compute it here from Date directly.
                let animPulse: Double
                if debugState.isComputing, let start = debugState.computeStartTime {
                    let raw = max(0, min(1, tl.date.timeIntervalSince(start) / debugState.computeDuration))
                    animPulse = raw < 0.5 ? 2*raw*raw : 1 - pow(-2*raw+2,2)/2  // ease-in-out
                } else {
                    animPulse = 1.0
                }

                // ── Background & Grid ─────────────────────────────────────────
                drawBackground(ctx: &ctx, size: size)
                drawGrid(ctx: &ctx, size: size)

                // ── Connections (bezier) ─────────────────────────────────────
                // Base alpha: 0.09/0.12 keeps connections visible on Retina (lineWidth ≥ 0.6pt)
                let breathe = debugState.isComputing ? 0.0 : 0.006 + sin(now*0.5)*0.004
                drawConnections(ctx: &ctx, from: nodes.input,  to: nodes.hidden, alpha: 0.09+breathe)
                drawConnections(ctx: &ctx, from: nodes.hidden, to: nodes.output, alpha: 0.12+breathe)

                // ── Sweep glow + boosted connections during compute ───────────
                if debugState.isComputing {
                    let w1t = max(0,min(1, animPulse/0.52))
                    let w1b = sin(w1t * .pi) * 0.32   // 3× brighter than before
                    if w1b > 0.001 {
                        drawConnections(ctx: &ctx, from: nodes.input, to: nodes.hidden, alpha: w1b)
                        drawSweepGlow(ctx: &ctx, fromX: nodes.input[0].x, toX: nodes.hidden[0].x,
                                      tNorm: w1t, boost: w1b, height: size.height)
                    }
                    if animPulse > 0.44 {
                        let w2t = max(0,min(1,(animPulse-0.44)/0.52))
                        let w2b = sin(w2t * .pi) * 0.38
                        if w2b > 0.001 {
                            drawConnections(ctx: &ctx, from: nodes.hidden, to: nodes.output, alpha: w2b)
                            drawSweepGlow(ctx: &ctx, fromX: nodes.hidden[0].x, toX: nodes.output[0].x,
                                          tNorm: w2t, boost: w2b, height: size.height)
                        }
                    }
                }

                // ── Idle particles (drift along W1 bezier paths) ──────────────
                if !debugState.isComputing {
                    for p in idleDefs {
                        var phase = (now * p.speed + p.phase).truncatingRemainder(dividingBy: 1.0)
                        if phase < 0 { phase += 1.0 }
                        let pos  = p.position(t: phase)
                        let fade = phase < 0.12 ? phase/0.12 : phase > 0.82 ? (1-phase)/0.18 : 1.0
                        // alpha 0.55 so particles are clearly visible on parchment background
                        drawGlowDot(ctx: &ctx, pos: pos, color: p.color, size: p.size, fade: fade*0.55)
                    }
                }

                // ── Forward particles (surge during compute) ──────────────────
                if debugState.isComputing {
                    for p in fwdW1 {
                        let t = animPulse/0.60 + p.phase
                        if t > 0 && t < 1 {
                            let fade = t < 0.08 ? t/0.08 : t > 0.88 ? (1-t)/0.12 : 1.0
                            drawGlowDot(ctx: &ctx, pos: p.position(t: t), color: p.color, size: p.size, fade: fade)
                        }
                    }
                    if animPulse > 0.38 {
                        for p in fwdW2 {
                            let t = (animPulse-0.44)/0.56 + p.phase
                            if t > 0 && t < 1 {
                                let fade = t < 0.08 ? t/0.08 : t > 0.88 ? (1-t)/0.12 : 1.0
                                drawGlowDot(ctx: &ctx, pos: p.position(t: t), color: p.color, size: p.size, fade: fade)
                            }
                        }
                    }
                }

                // ── Input nodes ───────────────────────────────────────────────
                let inputFlash = debugState.isComputing ? easeOut(max(0,min(1,animPulse*8))) : 1.0
                for (i,node) in nodes.input.enumerated() {
                    let val     = i < debugState.inputVector.count ? debugState.inputVector[i] : 0
                    let breathe = 1.0 + sin(now*0.65 + Double(i)*0.52)*0.09
                    drawNode(ctx:&ctx, x:node.x, y:node.y, radius:5.0*breathe,
                             color:node.color, activation:val*inputFlash)
                }

                // ── Hidden nodes ──────────────────────────────────────────────
                for (i,node) in nodes.hidden.enumerated() {
                    let val     = i < debugState.hiddenActivations.count ? debugState.hiddenActivations[i] : 0
                    let fireT   = debugState.isComputing ? easeOut(max(0,min(1,(animPulse-0.27)/0.09))) : 1.0
                    let breathe = 1.0 + sin(now*0.58 + Double(i)*0.41)*0.11
                    let color: Color = i < RECURRENT_SIZE
                        ? Color(red:0.61,green:0.50,blue:0.69)
                        : Color(red:0.55,green:0.44,blue:0.31)
                    drawNode(ctx:&ctx, x:node.x, y:node.y, radius:6.0*breathe,
                             color:color, activation:val*fireT)
                }

                // ── Recurrent bracket ─────────────────────────────────────────
                drawRecurrentAnnotation(ctx: &ctx, nodes: nodes, t: now)

                // ── Output gauges ─────────────────────────────────────────────
                let outT = debugState.isComputing ? easeOut(max(0,min(1,(animPulse-0.70)/0.24))) : 1.0
                for (i,node) in nodes.output.enumerated() {
                    let name  = i < SIGNAL_NAMES.count ? SIGNAL_NAMES[i] : ""
                    let val   = debugState.signals[name] ?? 0.5
                    let brth  = 1.0 + sin(now*0.52 + Double(i)*0.73)*0.08
                    let color = i < SIGNAL_COLORS.count ? SIGNAL_COLORS[i] : .gray
                    let sem   = i < SIGNAL_SEMANTICS.count ? SIGNAL_SEMANTICS[i] : ("lo","hi")
                    drawOutputGauge(ctx:&ctx, x:node.x, y:node.y, val:val, anim:outT*brth,
                                    color:color, name:name, semantics:sem)
                }

                // ── Labels ────────────────────────────────────────────────────
                drawLayerLabels(ctx: &ctx, nodes: nodes)
                drawGroupLabels(ctx: &ctx, nodes: nodes)
            }
        }
        .onAppear {
            bakeParticles()
            // Auto-demo: fire compute animation every 5s so the flow is visible without backend
            startDemoLoop()
        }
        .onChange(of: debugState.isComputing) { _, computing in
            if computing { rebakeForwardParticles() }
        }
        // Tap to manually trigger a demo compute step
        .onTapGesture { debugState.triggerDemo() }
    }

    // MARK: - Particle Baking (called once on appear, again each compute)

    private func bakeParticles() {
        let nodes = computeNodePositions(size: CGSize(width:600,height:500))
        guard !nodes.input.isEmpty, !nodes.hidden.isEmpty else { return }
        var s: UInt64 = 42
        func r() -> Double { s=s &* 6364136223846793005 &+ 1442695040888963407; return Double(s>>33)/Double(1<<31) }
        // 22 idle particles — larger size so they're clearly visible
        idleDefs = (0..<22).map { _ in
            makeDef(n1: nodes.input[Int(r()*Double(nodes.input.count))],
                    n2: nodes.hidden[Int(r()*Double(nodes.hidden.count))],
                    colorSrc: .input, size: CGFloat(2.5+r()*1.0), speed: 0.07+r()*0.05, phase: r())
        }
        rebakeForwardParticles()
    }

    /// Auto-play loop: fires demo compute every 5s so animation is visible without real backend.
    private func startDemoLoop() {
        func loop() {
            DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
                debugState.triggerDemo()
                loop()
            }
        }
        // First fire after 1s so the panel has time to lay out
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            debugState.triggerDemo()
            loop()
        }
    }

    private func rebakeForwardParticles() {
        let nodes = computeNodePositions(size: CGSize(width:600,height:500))
        guard !nodes.input.isEmpty, !nodes.hidden.isEmpty, !nodes.output.isEmpty else { return }
        var s: UInt64 = 137
        func r() -> Double { s=s &* 6364136223846793005 &+ 1442695040888963407; return Double(s>>33)/Double(1<<31) }
        fwdW1 = (0..<28).map { _ in
            makeDef(n1: nodes.input[Int(r()*Double(nodes.input.count))],
                    n2: nodes.hidden[Int(r()*Double(nodes.hidden.count))],
                    colorSrc: .input, size: CGFloat(1.8+r()*0.8), speed:0, phase: -(r()*0.6))
        }
        fwdW2 = (0..<18).map { _ in
            makeDef(n1: nodes.hidden[Int(r()*Double(nodes.hidden.count))],
                    n2: nodes.output[Int(r()*Double(nodes.output.count))],
                    colorSrc: .output, size: CGFloat(2.0+r()*0.8), speed:0, phase: -(r()*0.4))
        }
    }

    private enum ColorSrc { case input, output }
    private func makeDef(n1: NodeInfo, n2: NodeInfo, colorSrc: ColorSrc,
                         size: CGFloat, speed: Double, phase: Double) -> ParticleDef {
        let x1=n1.x+4, y1=n1.y, x2=n2.x-4, y2=n2.y, dx=x2-x1
        return ParticleDef(x1:x1,y1:y1,cp1x:x1+dx*0.4,cp1y:y1,cp2x:x1+dx*0.6,cp2y:y2,x2:x2,y2:y2,
                           color: colorSrc == .input ? n1.color : n2.color,
                           size:size, speed:speed, phase:phase)
    }

    // MARK: - Node Positions

    struct NodeInfo { let x,y: CGFloat; let color: Color }
    struct NodePositions { var input:[NodeInfo]=[]; var hidden:[NodeInfo]=[]; var output:[NodeInfo]=[] }

    private func computeNodePositions(size: CGSize) -> NodePositions {
        let w=size.width, h=size.height, lx:[CGFloat]=[52,w*0.40,w*0.70]
        var pos = NodePositions()
        let iSp=(h-100)/CGFloat(INPUT_SIZE+1)
        var idx=0
        for (count,color) in [(N_DRIVES,INPUT_GROUP_COLORS[0]),(N_PERCEPTION,INPUT_GROUP_COLORS[1]),
                               (N_RELATIONSHIP,INPUT_GROUP_COLORS[2]),(RECURRENT_SIZE,INPUT_GROUP_COLORS[3])] {
            for _ in 0..<count { pos.input.append(NodeInfo(x:lx[0],y:55+CGFloat(idx)*iSp,color:color)); idx+=1 }
        }
        let hSp=(h-90)/CGFloat(HIDDEN_SIZE+1)
        for i in 0..<HIDDEN_SIZE { pos.hidden.append(NodeInfo(x:lx[1],y:45+CGFloat(i)*hSp,color:Color(red:0.55,green:0.44,blue:0.31))) }
        let oSp=(h-120)/CGFloat(N_SIGNALS+1)
        for i in 0..<N_SIGNALS { pos.output.append(NodeInfo(x:lx[2],y:60+CGFloat(i+1)*oSp,color:i<SIGNAL_COLORS.count ? SIGNAL_COLORS[i]:.gray)) }
        return pos
    }

    // MARK: - Helpers

    private func easeOut(_ t:Double)->Double { 1-(1-t)*(1-t) }

    // MARK: - Draw Primitives

    private func drawBackground(ctx: inout GraphicsContext, size: CGSize) {
        let c=CGPoint(x:size.width*0.45,y:size.height*0.48)
        ctx.fill(Path(CGRect(origin:.zero,size:size)),
                 with:.radialGradient(Gradient(stops:[
                     .init(color:Color(red:0.96,green:0.92,blue:0.83),location:0),
                     .init(color:Color(red:0.93,green:0.88,blue:0.78),location:0.6),
                     .init(color:Color(red:0.88,green:0.80,blue:0.69),location:1.0),
                 ]), center:c, startRadius:0, endRadius:max(size.width,size.height)*0.72))
    }

    private func drawGrid(ctx: inout GraphicsContext, size: CGSize) {
        var p=Path(), x:CGFloat=0, y:CGFloat=0
        while x<size.width  { p.move(to:CGPoint(x:x,y:0)); p.addLine(to:CGPoint(x:x,y:size.height)); x+=38 }
        while y<size.height { p.move(to:CGPoint(x:0,y:y)); p.addLine(to:CGPoint(x:size.width,y:y)); y+=38 }
        ctx.stroke(p, with:.color(Color(red:0.55,green:0.39,blue:0.20).opacity(0.055)), lineWidth:0.3)
    }

    private func drawConnections(ctx: inout GraphicsContext, from:[NodeInfo], to:[NodeInfo], alpha:Double) {
        guard alpha>0.001 else { return }
        var pos=Path(), neg=Path()
        for (fi,f) in from.enumerated() {
            for (ti,t) in to.enumerated() {
                let x1=f.x+4, y1=f.y, x2=t.x-4, y2=t.y, dx=x2-x1
                let cp1=CGPoint(x:x1+dx*0.4,y:y1), cp2=CGPoint(x:x1+dx*0.6,y:y2)
                if (fi+ti)%3 != 0 { pos.move(to:CGPoint(x:x1,y:y1)); pos.addCurve(to:CGPoint(x:x2,y:y2),control1:cp1,control2:cp2) }
                else               { neg.move(to:CGPoint(x:x1,y:y1)); neg.addCurve(to:CGPoint(x:x2,y:y2),control1:cp1,control2:cp2) }
            }
        }
        // lineWidth ≥ 0.6pt ensures visibility on Retina (0.28pt = sub-pixel, never renders)
        ctx.stroke(pos, with:.color(BRASS.opacity(alpha)), lineWidth:0.6)
        ctx.stroke(neg, with:.color(Color(red:0.35,green:0.41,blue:0.49).opacity(alpha*0.55)), lineWidth:0.5)
    }

    private func drawSweepGlow(ctx: inout GraphicsContext, fromX:CGFloat, toX:CGFloat,
                                tNorm:Double, boost:Double, height:CGFloat) {
        let wx=fromX+CGFloat(tNorm)*(toX-fromX)
        let g=Color(red:0.94,green:0.78,blue:0.47)
        ctx.fill(Path(CGRect(x:wx-90,y:0,width:180,height:height)),
                 with:.linearGradient(Gradient(stops:[
                     .init(color:g.opacity(0),         location:0),
                     .init(color:g.opacity(boost*0.22),location:0.38),
                     .init(color:g.opacity(boost*0.30),location:0.50),
                     .init(color:g.opacity(boost*0.22),location:0.62),
                     .init(color:g.opacity(0),         location:1),
                 ]), startPoint:CGPoint(x:wx-90,y:0), endPoint:CGPoint(x:wx+90,y:0)))
    }

    private func drawDot(ctx: inout GraphicsContext, pos:CGPoint, color:Color, size:CGFloat, alpha:Double) {
        ctx.fill(Path(ellipseIn:CGRect(x:pos.x-size,y:pos.y-size,width:size*2,height:size*2)),
                 with:.color(color.opacity(alpha)))
    }

    private func drawGlowDot(ctx: inout GraphicsContext, pos:CGPoint, color:Color, size:CGFloat, fade:Double) {
        let gR=size*4
        ctx.fill(Path(ellipseIn:CGRect(x:pos.x-gR,y:pos.y-gR,width:gR*2,height:gR*2)),
                 with:.radialGradient(Gradient(stops:[
                     .init(color:color.opacity(fade*0.35),location:0),
                     .init(color:color.opacity(0),        location:1),
                 ]), center:pos, startRadius:0, endRadius:gR))
        ctx.fill(Path(ellipseIn:CGRect(x:pos.x-size,y:pos.y-size,width:size*2,height:size*2)),
                 with:.color(color.opacity(fade*0.85)))
    }

    private func drawNode(ctx: inout GraphicsContext, x:CGFloat, y:CGFloat,
                          radius:CGFloat, color:Color, activation:Double) {
        let pt=CGPoint(x:x,y:y), a=min(1,abs(activation))
        let hR=radius*2.2
        ctx.fill(Path(ellipseIn:CGRect(x:x-hR,y:y-hR,width:hR*2,height:hR*2)),
                 with:.radialGradient(Gradient(stops:[
                     .init(color:color.opacity(0.30+a*0.30),location:0),
                     .init(color:color.opacity(0),location:1),
                 ]), center:pt, startRadius:0, endRadius:hR))
        let cR=radius*0.88
        ctx.fill(Path(ellipseIn:CGRect(x:x-cR,y:y-cR,width:cR*2,height:cR*2)),
                 with:.color(color.opacity(0.28+a*0.72)))
        ctx.stroke(Path(ellipseIn:CGRect(x:x-cR,y:y-cR,width:cR*2,height:cR*2)),
                   with:.color(BRASS.opacity(0.28+a*0.28)), lineWidth:0.6)
        if a > 0.3 {
            let cold=min(1.0,(a-0.3)/0.7), cR2=radius*2.6
            let cc=Color(red:0.59+cold*0.31,green:0.80+cold*0.12,blue:0.95)
            ctx.fill(Path(ellipseIn:CGRect(x:x-cR2,y:y-cR2,width:cR2*2,height:cR2*2)),
                     with:.radialGradient(Gradient(stops:[
                         .init(color:cc.opacity(cold*0.48),location:0),
                         .init(color:cc.opacity(cold*0.12),location:0.45),
                         .init(color:cc.opacity(0),location:1),
                     ]), center:pt, startRadius:0, endRadius:cR2))
        }
    }

    private func drawOutputGauge(ctx: inout GraphicsContext, x:CGFloat, y:CGFloat,
                                  val:Double, anim:Double, color:Color, name:String, semantics:(String,String)) {
        let bR:CGFloat=10, oR:CGFloat=13, pt=CGPoint(x:x,y:y)
        ctx.stroke(Path(ellipseIn:CGRect(x:x-oR,y:y-oR,width:oR*2,height:oR*2)),
                   with:.color(BRASS.opacity(0.38+anim*0.22)), lineWidth:1.2)
        for tick in 0..<12 {
            let angle=Double(tick)/12.0 * .pi*2 - .pi/2, maj=tick%3==0
            let iR=oR-(maj ? 4.0:2.2)
            var tp=Path()
            tp.move(to:    CGPoint(x:x+CGFloat(cos(angle))*iR,  y:y+CGFloat(sin(angle))*iR))
            tp.addLine(to: CGPoint(x:x+CGFloat(cos(angle))*oR,  y:y+CGFloat(sin(angle))*oR))
            ctx.stroke(tp, with:.color(BRASS.opacity(maj ? 0.52:0.22)), lineWidth:maj ? 0.8:0.4)
        }
        ctx.fill(Path(ellipseIn:CGRect(x:x-bR,y:y-bR,width:bR*2,height:bR*2)),
                 with:.color(Color(red:0.04,green:0.02,blue:0.01).opacity(0.78)))
        if anim > 0.02 {
            let sA = -0.9 * Double.pi, arcA=val*1.8 * .pi*anim, arcR=bR*0.75
            var sec=Path(); sec.move(to:pt)
            sec.addArc(center:pt,radius:arcR,startAngle:.radians(sA),endAngle:.radians(sA+arcA),clockwise:false)
            sec.closeSubpath()
            ctx.fill(sec, with:.color(Color(red:0.43,green:0.73,blue:1.0).opacity(0.08+anim*0.16)))
            var arc=Path()
            arc.addArc(center:pt,radius:arcR,startAngle:.radians(sA),endAngle:.radians(sA+arcA),clockwise:false)
            ctx.stroke(arc, with:.color(Color(red:0.69,green:0.86,blue:1.0).opacity(0.55+anim*0.38)), lineWidth:1.3)
        }
        ctx.draw(Text(String(format:"%.2f",val)).font(.system(size:6.5,weight:.bold,design:.monospaced))
                    .foregroundColor(Color(red:0.69,green:0.86,blue:1.0).opacity(0.45+anim*0.45)),
                 at:CGPoint(x:x,y:y+2), anchor:.center)
        let nx=x+oR+7
        ctx.draw(Text(name).font(.system(size:10,weight:.medium)).foregroundColor(INK.opacity(0.38+val*0.42)),
                 at:CGPoint(x:nx,y:y-3), anchor:.leading)
        ctx.draw(Text("\(semantics.0) ↔ \(semantics.1)").font(.system(size:7.5,design:.monospaced))
                    .foregroundColor(INK.opacity(0.28)),
                 at:CGPoint(x:nx,y:y+9), anchor:.leading)
    }

    private func drawRecurrentAnnotation(ctx: inout GraphicsContext, nodes:NodePositions, t:Double) {
        guard nodes.hidden.count>=RECURRENT_SIZE,
              nodes.input.count>=N_DRIVES+N_CONTEXT+RECURRENT_SIZE else { return }
        let pulse=0.28+sin(t*1.1)*0.08
        let h0=nodes.hidden[0], h7=nodes.hidden[RECURRENT_SIZE-1], hx=h0.x
        let lav=Color(red:0.61,green:0.50,blue:0.72)
        var br=Path()
        br.move(to:CGPoint(x:hx+10,y:h0.y-6)); br.addLine(to:CGPoint(x:hx+17,y:h0.y-6))
        br.addLine(to:CGPoint(x:hx+17,y:h7.y+6)); br.addLine(to:CGPoint(x:hx+10,y:h7.y+6))
        ctx.stroke(br, with:.color(lav.opacity(pulse*0.50)), style:StrokeStyle(lineWidth:0.8,dash:[2,3]))
        ctx.draw(Text("t+1 →").font(.system(size:7,design:.monospaced)).foregroundColor(lav.opacity(pulse)),
                 at:CGPoint(x:hx+20,y:(h0.y+h7.y)/2+3), anchor:.leading)
        let r0=nodes.input[N_DRIVES+N_CONTEXT], rN=nodes.input[N_DRIVES+N_CONTEXT+RECURRENT_SIZE-1]
        ctx.draw(Text("← t-1").font(.system(size:7,design:.monospaced)).foregroundColor(lav.opacity(pulse*0.80)),
                 at:CGPoint(x:r0.x-6,y:(r0.y+rN.y)/2+3), anchor:.trailing)
    }

    private func drawLayerLabels(ctx: inout GraphicsContext, nodes:NodePositions) {
        let labels: [(String, CGFloat)] = [
            ("INPUT",  nodes.input.first?.x  ?? 52),
            ("HIDDEN", nodes.hidden.first?.x ?? 240),
            ("OUTPUT", nodes.output.first?.x ?? 420),
        ]
        for (text, x) in labels {
            ctx.draw(Text(text).font(.system(size:8,weight:.medium,design:.monospaced)).foregroundColor(INK.opacity(0.15)),
                     at:CGPoint(x:x-18,y:18), anchor:.leading)
        }
    }

    private func drawGroupLabels(ctx: inout GraphicsContext, nodes:NodePositions) {
        guard nodes.input.count>=INPUT_SIZE else { return }
        let defs:[( String,Int,Int,Color)] = [
            ("DRIVES",    0,                         N_DRIVES-1,                         INPUT_GROUP_COLORS[0]),
            ("CONTEXT",   N_DRIVES,                  N_DRIVES+N_CONTEXT-1,               INPUT_GROUP_COLORS[1]),
            ("RELATION",  N_DRIVES+N_CONTEXT,        N_DRIVES+N_CONTEXT+N_RELATIONSHIP-1,INPUT_GROUP_COLORS[2]),
            ("RECURRENT", N_DRIVES+N_CONTEXT+N_RELATIONSHIP, INPUT_SIZE-1,              INPUT_GROUP_COLORS[3]),
        ]
        for (label,s,e,color) in defs {
            guard e<nodes.input.count else { continue }
            let midY=(nodes.input[s].y+nodes.input[e].y)/2
            var c2=ctx
            c2.translateBy(x:nodes.input[0].x-22, y:midY)
            c2.rotate(by:.degrees(-90))
            c2.draw(Text(label).font(.system(size:7,weight:.medium,design:.monospaced)).foregroundColor(color.opacity(0.42)),
                    at:.zero, anchor:.center)
        }
    }
}
