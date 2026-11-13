// Live camera for the FPO agent screen: video preview, capture button, retake. Owner: Anirudh (agent screen), written by Darshan.
//
// The photo is taken from the camera stream, never from a file picker. At the moment of capture it also records the time and
// the GPS fix (the backend checks the location is within 500 m of the pickup point and the photo is under 10 minutes old).
// Needs a secure page (https or localhost). If the camera cannot start (no camera, permission denied, plain http), a clearly
// labelled fallback lets the phone's own camera app take the picture; a laptop without a camera shows an explanation instead.
import { useCallback, useEffect, useRef, useState } from "react";

export interface CaptureMeta {
  capturedAt: string; // ISO time of the shot
  lat?: number;
  lon?: number;
  accuracy?: number; // metres
}

interface Props {
  preview: string | null; // data URL of the photo already taken, if any
  onCapture: (file: File, dataUrl: string, meta: CaptureMeta) => void;
  onClear: () => void; // "Retake"
}

const MAX_BYTES = 1_800_000; // the server accepts 2 MB
const MAX_WIDTH = 1280;

function readAsDataUrl(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

function currentPosition(): Promise<GeolocationPosition | null> {
  if (!navigator.geolocation) return Promise.resolve(null);
  return new Promise((resolve) =>
    navigator.geolocation.getCurrentPosition(resolve, () => resolve(null), {
      enableHighAccuracy: true,
      timeout: 8000,
      maximumAge: 0,
    }),
  );
}

export default function LiveCamera({ preview, onCapture, onClear }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fallbackRef = useRef<HTMLInputElement | null>(null);
  const [facing, setFacing] = useState<"environment" | "user">("environment");
  const [state, setState] = useState<"starting" | "live" | "error">("starting");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  const start = useCallback(
    async (mode: "environment" | "user") => {
      stop();
      setState("starting");
      setMessage("");
      if (!navigator.mediaDevices?.getUserMedia) {
        setMessage(
          window.isSecureContext
            ? "This browser cannot use the camera."
            : "The camera only works on a secure page. Open this app through the https address (or localhost).",
        );
        setState("error");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: mode }, width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
        streamRef.current = stream;
        const v = videoRef.current;
        if (v) {
          v.srcObject = stream;
          await v.play().catch(() => undefined);
        }
        setState("live");
      } catch (e: any) {
        setMessage(
          e?.name === "NotAllowedError"
            ? "Camera permission was denied. Allow the camera for this site in the browser, then tap Try again."
            : e?.name === "NotFoundError"
              ? "No camera was found on this device."
              : "Could not start the camera.",
        );
        setState("error");
      }
    },
    [stop],
  );

  // The camera runs while there is no photo; it is released as soon as a photo is taken or the screen closes.
  useEffect(() => {
    if (!preview) void start(facing);
    else stop();
    return stop;
  }, [preview, facing, start, stop]);

  const capture = async () => {
    const v = videoRef.current;
    if (!v || state !== "live" || !v.videoWidth || busy) return;
    setBusy(true);
    const scale = Math.min(1, MAX_WIDTH / v.videoWidth);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(v.videoWidth * scale);
    canvas.height = Math.round(v.videoHeight * scale);
    canvas.getContext("2d")!.drawImage(v, 0, 0, canvas.width, canvas.height);
    const capturedAt = new Date().toISOString();

    let blob: Blob | null = null;
    let quality = 0.85;
    for (; quality >= 0.4; quality -= 0.15) {
      blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/jpeg", quality));
      if (blob && blob.size <= MAX_BYTES) break;
    }
    if (!blob) {
      setMessage("Could not take the photo. Try again.");
      setBusy(false);
      return;
    }
    const pos = await currentPosition(); // the GPS fix belongs to this very photo
    const meta: CaptureMeta = { capturedAt };
    if (pos) {
      meta.lat = pos.coords.latitude;
      meta.lon = pos.coords.longitude;
      meta.accuracy = pos.coords.accuracy;
    }
    const file = new File([blob], `produce-${Date.now()}.jpg`, { type: "image/jpeg" });
    onCapture(file, await readAsDataUrl(blob), meta);
    setBusy(false);
  };

  const useDeviceCameraApp = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const pos = await currentPosition();
    const meta: CaptureMeta = { capturedAt: new Date().toISOString() };
    if (pos) {
      meta.lat = pos.coords.latitude;
      meta.lon = pos.coords.longitude;
      meta.accuracy = pos.coords.accuracy;
    }
    onCapture(file, await readAsDataUrl(file), meta);
  };

  if (preview) {
    return (
      <div className="relative rounded-xl overflow-hidden border border-slate-700 aspect-video bg-black flex items-center justify-center">
        <img src={preview} alt="Captured produce" className="max-h-full object-contain" />
        <button
          type="button"
          onClick={onClear}
          className="absolute bottom-2 right-2 bg-slate-900/85 hover:bg-slate-800 text-white text-xs font-semibold px-3 py-2 rounded-full border border-slate-600"
        >
          Retake photo
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="relative rounded-xl overflow-hidden border border-slate-700 aspect-video bg-black">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          data-testid="live-camera"
          className={`w-full h-full object-cover ${state === "live" ? "" : "invisible"}`}
        />
        {state === "starting" && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-300">Starting camera...</div>
        )}
        {state === "error" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center">
            <p className="text-sm text-slate-200">{message}</p>
            <div className="flex flex-wrap items-center justify-center gap-2">
              <button
                type="button"
                onClick={() => void start(facing)}
                className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold px-3 py-2 rounded-lg"
              >
                Try again
              </button>
              <button
                type="button"
                onClick={() => fallbackRef.current?.click()}
                className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold px-3 py-2 rounded-lg border border-slate-600"
              >
                Use the phone's camera app instead
              </button>
            </div>
          </div>
        )}
        {state === "live" && (
          <>
            <button
              type="button"
              onClick={() => setFacing((f) => (f === "environment" ? "user" : "environment"))}
              className="absolute top-2 right-2 bg-slate-900/70 hover:bg-slate-800 text-white text-[11px] font-semibold px-2.5 py-1.5 rounded-full border border-slate-600"
            >
              Switch camera
            </button>
            <button
              type="button"
              onClick={() => void capture()}
              disabled={busy}
              aria-label="Take photo"
              className="absolute bottom-3 left-1/2 -translate-x-1/2 w-16 h-16 rounded-full bg-white/90 border-4 border-emerald-500 shadow-lg active:scale-95 disabled:opacity-60"
            />
          </>
        )}
      </div>
      <p className="text-[11px] text-slate-500 text-center">
        {state === "live" ? "Frame the produce in the live view, then press the round button." : "The photo must be taken with the camera, at the yard."}
      </p>
      <input ref={fallbackRef} type="file" accept="image/*" capture="environment" onChange={useDeviceCameraApp} className="hidden" />
    </div>
  );
}
