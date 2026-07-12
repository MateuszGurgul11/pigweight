import type { PredictMask } from './backendClient'

/**
 * Rysuje wynik predykcji (polygon + bbox) na kontekście canvasa.
 * Współrzędne maski/bboxa są w pikselach klatki, którą wysłaliśmy do backendu —
 * rozmiar canvasa MUSI być zgodny z tym kadrem (CameraView/TestView pilnują
 * tego sami).
 */
export function drawPrediction(
  ctx: CanvasRenderingContext2D,
  mask: PredictMask,
  source: 'camera' | 'upload' = 'camera',
): void {
  const { polygon, bbox } = mask
  const lineWidth = Math.max(2, ctx.canvas.width / 250)
  const color = source === 'camera' ? '#facc15' : '#4ade80'

  if (polygon.length >= 3) {
    ctx.save()
    ctx.fillStyle = 'rgba(250, 204, 21, 0.22)'
    ctx.strokeStyle = color
    ctx.lineWidth = lineWidth
    ctx.beginPath()
    const [x0, y0] = polygon[0]!
    ctx.moveTo(x0, y0)
    for (let i = 1; i < polygon.length; i++) {
      const [x, y] = polygon[i]!
      ctx.lineTo(x, y)
    }
    ctx.closePath()
    ctx.fill()
    ctx.stroke()
    ctx.restore()
  }

  ctx.save()
  ctx.strokeStyle = color
  ctx.lineWidth = lineWidth
  ctx.strokeRect(bbox.x, bbox.y, bbox.w, bbox.h)
  ctx.restore()
}
