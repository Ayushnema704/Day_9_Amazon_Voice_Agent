"use client";

// Import the runtime patch so it runs in the browser environment before
// any LiveKit components mount. This prevents duplicate text-stream handler
// registration errors across React StrictMode double-mounts.
import '@/lib/livekit-patches';

export default function LiveKitPatchesClient() {
  // This component intentionally renders nothing; its module import side-
  // effects perform the patch. Log once so we can confirm it ran in the browser.
  if (typeof window !== 'undefined' && (window as any).console) {
    // eslint-disable-next-line no-console
    console.info('[livekit-patches] client patch mounted');
  }
  return null;
}
