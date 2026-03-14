import SwiftUI

/// Full-screen image zoom overlay — click background to dismiss.
/// Supports both URL-loaded images and NSImage instances.
struct ImageZoomOverlay: View {
    let imageURL: URL?
    let nsImage: NSImage?
    let onDismiss: () -> Void

    init(url: URL? = nil, nsImage: NSImage? = nil, onDismiss: @escaping () -> Void) {
        self.imageURL = url
        self.nsImage = nsImage
        self.onDismiss = onDismiss
    }

    var body: some View {
        ZStack {
            // Dimmed background — tap to dismiss
            Color.black.opacity(0.75)
                .ignoresSafeArea()
                .onTapGesture { onDismiss() }

            // Zoomed image
            Group {
                if let nsImage = nsImage {
                    Image(nsImage: nsImage)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                } else if let url = imageURL {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                        case .failure:
                            Image(systemName: "photo")
                                .font(.system(size: 48))
                                .foregroundStyle(.white.opacity(0.5))
                        case .empty:
                            ProgressView()
                                .tint(.white)
                        @unknown default:
                            EmptyView()
                        }
                    }
                }
            }
            .padding(40)
            .shadow(color: .black.opacity(0.4), radius: 20, y: 8)
        }
        .transition(.opacity)
    }
}
