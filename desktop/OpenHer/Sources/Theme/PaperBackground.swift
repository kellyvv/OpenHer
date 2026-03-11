import SwiftUI

/// Paper background — warm parchment solid color.
struct PaperBackground: View {
    var body: some View {
        Paper.background
            .ignoresSafeArea()
    }
}
