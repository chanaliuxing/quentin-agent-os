/**
 * Quentin Canvas Renderer
 * Handles rendering of screen frames and AI visual reasoning overlays.
 */

export interface BoundingBox {
    x: number;
    y: number;
    width: number;
    height: number;
    label: string;
    color: string;
}

export class CanvasRenderer {
    private ctx: CanvasRenderingContext2D;
    private canvas: HTMLCanvasElement;

    constructor(canvas: HTMLCanvasElement) {
        this.canvas = canvas;
        const context = canvas.getContext('2d');
        if (!context) throw new Error("Could not get 2D context");
        this.ctx = context;
    }

    /**
     * Renders a Base64 frame to the canvas.
     */
    public async drawFrame(base64Image: string): Promise<void> {
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => {
                // Adjust canvas size to match image aspect ratio
                this.canvas.width = img.width;
                this.canvas.height = img.height;
                this.ctx.drawImage(img, 0, 0);
                resolve();
            };
            img.src = `data:image/jpeg;base64,${base64Image}`;
        });
    }

    /**
     * Draws bounding boxes over the frame.
     */
    public drawOverlays(boxes: BoundingBox[]): void {
        boxes.forEach(box => {
            this.ctx.strokeStyle = box.color || 'red';
            this.ctx.lineWidth = 3;
            this.ctx.strokeRect(box.x, box.y, box.width, box.height);

            // Draw label
            this.ctx.fillStyle = box.color || 'red';
            this.ctx.font = '16px Arial';
            this.ctx.fillText(box.label, box.x, box.y - 5);
        });
    }

    /**
     * Map screen coordinates back to node coordinates.
     */
    public getRelativeCoords(clientX: number, clientY: number): {x: number, y: number} {
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        return {
            x: Math.round((clientX - rect.left) * scaleX),
            y: Math.round((clientY - rect.top) * scaleY)
        };
    }
}
