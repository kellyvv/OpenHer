import AppKit
import Vision
import CoreImage
import CoreImage.CIFilterBuiltins

/// Generates a "dormant" version of a persona image where only the person
/// is desaturated while the cabinet frame and background remain full-color.
enum PersonaDormantEffect {

    /// Applies person-only desaturation to the given image.
    /// Uses Vision's person segmentation to create a mask, then composites
    /// a desaturated version of the person over the full-color background.
    ///
    /// Returns the original image if segmentation fails.
    static func apply(to image: NSImage) -> NSImage {
        guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
            return image
        }

        // 1. Generate person segmentation mask
        let request = VNGeneratePersonSegmentationRequest()
        request.qualityLevel = .accurate
        // Request full-resolution mask output
        request.outputPixelFormat = kCVPixelFormatType_OneComponent8
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])

        do {
            try handler.perform([request])
        } catch {
            print("[PersonaDormantEffect] Segmentation failed: \(error)")
            return image
        }

        guard let result = request.results?.first else {
            return image
        }

        let maskPixelBuffer = result.pixelBuffer

        // 2. Create CIImages
        let ciContext = CIContext()
        let originalCI = CIImage(cgImage: cgImage)
        let rawMask = CIImage(cvPixelBuffer: maskPixelBuffer)

        // Scale mask to match original image size using Lanczos for sharper edges
        let scaleX = originalCI.extent.width / rawMask.extent.width
        let scaleY = originalCI.extent.height / rawMask.extent.height
        let scaledMask = rawMask
            .transformed(by: CGAffineTransform(scaleX: scaleX, y: scaleY))
            .samplingNearest()

        // 3. Sharpen mask — apply threshold to make it binary (hard edges)
        // This prevents the soft mask edges from bleeding desaturation into the cabinet
        let threshold: Float = 0.5
        let sharpenedMask = scaledMask.applyingFilter("CIColorClamp", parameters: [
            "inputMinComponents": CIVector(x: 0, y: 0, z: 0, w: 0),
            "inputMaxComponents": CIVector(x: 1, y: 1, z: 1, w: 1)
        ]).applyingFilter("CIColorMatrix", parameters: [
            // Boost contrast: multiply by high value then clamp
            "inputRVector": CIVector(x: CGFloat(1.0 / threshold), y: 0, z: 0, w: 0),
            "inputGVector": CIVector(x: 0, y: CGFloat(1.0 / threshold), z: 0, w: 0),
            "inputBVector": CIVector(x: 0, y: 0, z: CGFloat(1.0 / threshold), w: 0),
            "inputAVector": CIVector(x: 0, y: 0, z: 0, w: CGFloat(1.0 / threshold)),
            "inputBiasVector": CIVector(x: CGFloat(-0.5 / threshold + 0.5), y: CGFloat(-0.5 / threshold + 0.5), z: CGFloat(-0.5 / threshold + 0.5), w: CGFloat(-0.5 / threshold + 0.5))
        ]).applyingFilter("CIColorClamp", parameters: [
            "inputMinComponents": CIVector(x: 0, y: 0, z: 0, w: 0),
            "inputMaxComponents": CIVector(x: 1, y: 1, z: 1, w: 1)
        ])

        // 4. Create desaturated version of the person
        let desaturated = originalCI.applyingFilter("CIColorControls", parameters: [
            kCIInputSaturationKey: 0.1,
            kCIInputBrightnessKey: -0.02
        ])

        // 5. Composite: use mask to blend desaturated person over full-color background
        // Where mask is white (person) → use desaturated; where black (bg) → use original
        let blended = desaturated.applyingFilter("CIBlendWithMask", parameters: [
            kCIInputBackgroundImageKey: originalCI,
            kCIInputMaskImageKey: sharpenedMask
        ])

        // 6. Render to NSImage
        guard let outputCG = ciContext.createCGImage(blended, from: originalCI.extent) else {
            return image
        }

        return NSImage(cgImage: outputCG, size: image.size)
    }
}
