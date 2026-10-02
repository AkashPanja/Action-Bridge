import { useCallback, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import "react-easy-crop/react-easy-crop.css";
import { Crop, ZoomIn } from "lucide-react";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";

const ASPECTS = [
  { label: "Original", value: 0 },
  { label: "Square 1:1", value: 1 },
  { label: "Wide 4:1", value: 4 },
  { label: "Classic 4:3", value: 4 / 3 },
];

const MAX_DIMENSION = 1024;

async function getCroppedBlob(imageSrc: string, pixels: Area): Promise<Blob> {
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = imageSrc;
  });

  const scale = Math.min(1, MAX_DIMENSION / Math.max(pixels.width, pixels.height));
  const outW = Math.max(1, Math.round(pixels.width * scale));
  const outH = Math.max(1, Math.round(pixels.height * scale));

  const canvas = document.createElement("canvas");
  canvas.width = outW;
  canvas.height = outH;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas is not available");

  ctx.drawImage(
    image,
    pixels.x, pixels.y, pixels.width, pixels.height,
    0, 0, outW, outH,
  );

  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/png"),
  );
  if (!blob) throw new Error("Could not process image");
  return blob;
}

interface LogoCropperProps {
  imageSrc: string;
  open: boolean;
  onClose: () => void;
  onConfirm: (blob: Blob, width: number, height: number) => void;
}

export function LogoCropper({ imageSrc, open, onClose, onConfirm }: LogoCropperProps) {
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [aspectIndex, setAspectIndex] = useState(0);
  const [naturalAspect, setNaturalAspect] = useState(4 / 3);
  const [pixels, setPixels] = useState<Area | null>(null);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState("");

  const aspect = ASPECTS[aspectIndex].value || naturalAspect;

  const onCropComplete = useCallback((_area: Area, areaPixels: Area) => {
    setPixels(areaPixels);
  }, []);

  async function handleConfirm() {
    if (!pixels) return;
    setError("");
    setProcessing(true);
    try {
      const blob = await getCroppedBlob(imageSrc, pixels);
      const scale = Math.min(1, MAX_DIMENSION / Math.max(pixels.width, pixels.height));
      onConfirm(blob, Math.round(pixels.width * scale), Math.round(pixels.height * scale));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not crop image");
      setProcessing(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => { if (!o) onClose(); }}
      title="Crop your logo"
      description="Drag to reposition, scroll or use the slider to zoom. The result is resized to a maximum of 1024 px."
      className="max-w-2xl"
    >
      <div className="relative h-72 w-full overflow-hidden rounded-xl bg-surface-100 dark:bg-surface-900 sm:h-80">
        <Cropper
          image={imageSrc}
          crop={crop}
          zoom={zoom}
          aspect={aspect}
          onCropChange={setCrop}
          onZoomChange={setZoom}
          onCropComplete={onCropComplete}
          onMediaLoaded={(media) => {
            if (media.naturalWidth && media.naturalHeight) {
              setNaturalAspect(media.naturalWidth / media.naturalHeight);
            }
          }}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {ASPECTS.map((a, i) => (
          <button
            key={a.label}
            type="button"
            onClick={() => setAspectIndex(i)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
              i === aspectIndex
                ? "bg-brand-600 text-white shadow-md shadow-brand-600/25"
                : "bg-surface-100 text-surface-600 hover:bg-surface-200 dark:bg-surface-700 dark:text-surface-300 dark:hover:bg-surface-600"
            }`}
          >
            {a.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 text-surface-500">
          <ZoomIn className="h-4 w-4" />
          <input
            type="range"
            min={1}
            max={3}
            step={0.05}
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
            className="w-32 accent-brand-600"
            aria-label="Zoom"
          />
        </div>
      </div>

      {error ? (
        <p className="mt-3 rounded-xl bg-accent-50 px-4 py-2 text-sm text-accent-600 dark:bg-accent-900/20 dark:text-accent-400">
          {error}
        </p>
      ) : null}

      <div className="mt-5 flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onClose} disabled={processing}>
          Cancel
        </Button>
        <Button type="button" onClick={handleConfirm} isLoading={processing} disabled={!pixels}>
          <Crop className="h-4 w-4" /> Use this logo
        </Button>
      </div>
    </Dialog>
  );
}
