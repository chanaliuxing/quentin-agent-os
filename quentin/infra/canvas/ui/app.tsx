import React, { useEffect, useRef, useState } from 'react';
import { CanvasRenderer, BoundingBox } from './renderer';

const CanvasApp: React.FC = () => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [renderer, setRenderer] = useState<CanvasRenderer | null>(null);
    const [socket, setSocket] = useState<WebSocket | null>(null);
    const [currentNodeId, setCurrentNodeId] = useState<string>('');
    const [status, setStatus] = useState<string>('Disconnected');
    const [uiTree, setUiTree] = useState<any>(null);
    const [spans, setSpans] = useState<any[]>([]); 
    const [pendingApproval, setPendingApproval] = useState<any>(null);

    // Atomic Level: Non-blocking Frame Queue (OpenClaw Parity)
    const frameQueue = useRef<string | null>(null);

    useEffect(() => {
        if (canvasRef.current && !renderer) {
            setRenderer(new CanvasRenderer(canvasRef.current));
        }

        // Dedicated rendering loop to avoid React render cycle bottlenecks
        let animationFrameId: number;
        const renderLoop = async () => {
            if (renderer && frameQueue.current) {
                const nextFrame = frameQueue.current;
                frameQueue.current = null; // Clear queue
                await renderer.drawFrame(nextFrame);
            }
            animationFrameId = requestAnimationFrame(renderLoop);
        };
        animationFrameId = requestAnimationFrame(renderLoop);

        const ws = new WebSocket(`ws://${window.location.host}/ws/canvas`);
        ws.onopen = () => setStatus('Connected');
        ws.onclose = () => setStatus('Disconnected');
        
        ws.onmessage = async (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'node_event' && data.event === 'screen_frame') {
                setCurrentNodeId(data.node_id);
                // Atomic: Instead of await draw, we push to the non-blocking queue
                frameQueue.current = data.payload.image;
                
                if (data.payload.ui_tree) {
                    setUiTree(data.payload.ui_tree);
                }
            }
            
            if (data.type === 'approval_request') setPendingApproval(data.payload);
            if (data.type === 'telemetry_span') setSpans(prev => [data.payload, ...prev].slice(0, 50));
        };

        setSocket(ws);
        return () => {
            ws.close();
            cancelAnimationFrame(animationFrameId);
        };
    }, [renderer]);

    const resolveApproval = (decision: boolean) => {
        if (!socket || !pendingApproval) return;
        socket.send(JSON.stringify({
            command: 'resolve_approval',
            request_id: pendingApproval.request_id,
            decision: decision
        }));
        setPendingApproval(null);
    };

    const handleCanvasClick = (e: React.MouseEvent) => {
        if (!renderer || !socket || !currentNodeId) return;
        const coords = renderer.getRelativeCoords(e.clientX, e.clientY);
        socket.send(JSON.stringify({
            command: 'click',
            node_id: currentNodeId,
            coords: [coords.x, coords.y]
        }));
    };

    return (
        <div className="canvas-container" style={{ display: 'flex', padding: '20px', fontFamily: 'monospace', height: '90vh' }}>
            {pendingApproval && (
                <div style={{ position: 'fixed', top: '20%', left: '50%', transform: 'translateX(-50%)', background: 'white', border: '3px solid red', padding: '30px', zIndex: 1000, boxShadow: '0 0 40px rgba(0,0,0,0.7)', borderRadius: '8px' }}>
                    <h2 style={{ color: 'red', marginTop: 0 }}>⚠️ SECURITY APPROVAL</h2>
                    <hr/>
                    <p>AI Tool: <strong style={{ color: 'blue' }}>{pendingApproval.tool}</strong></p>
                    <p><strong>Reason:</strong> {pendingApproval.reason}</p>
                    <div style={{ display: 'flex', gap: '20px', marginTop: '20px' }}>
                        <button onClick={() => resolveApproval(true)} style={{ background: '#28a745', color: 'white', border: 'none', padding: '12px 30px', cursor: 'pointer', fontWeight: 'bold' }}>APPROVE</button>
                        <button onClick={() => resolveApproval(false)} style={{ background: '#dc3545', color: 'white', border: 'none', padding: '12px 30px', cursor: 'pointer', fontWeight: 'bold' }}>REJECT</button>
                    </div>
                </div>
            )}

            <div className="main-panel" style={{ flex: 3, display: 'flex', flexDirection: 'column' }}>
                <header style={{ marginBottom: '10px', display: 'flex', justifyContent: 'space-between' }}>
                    <div><strong>Quentin Canvas</strong> | Node: {currentNodeId || 'None'}</div>
                    <div style={{ color: status === 'Connected' ? 'green' : 'red' }}>● {status}</div>
                </header>
                <div style={{ border: '2px solid #333', display: 'inline-block', position: 'relative', overflow: 'auto', backgroundColor: '#000' }}>
                    <canvas ref={canvasRef} onClick={handleCanvasClick} style={{ cursor: 'crosshair', maxWidth: '100%', height: 'auto', display: 'block' }}/>
                </div>
                <div className="telemetry-panel" style={{ marginTop: '20px', height: '150px', overflowY: 'auto', borderTop: '1px solid #eee', padding: '10px', background: '#f9f9f9' }}>
                    <strong>Telemetry Stream:</strong>
                    {spans.map((span, i) => (
                        <div key={i} style={{ fontSize: '11px', color: span.status === 'error' ? 'red' : '#444', borderBottom: '1px solid #eee', padding: '2px 0' }}>
                            [{span.status.toUpperCase()}] {span.name} ({span.duration_ms.toFixed(1)}ms)
                        </div>
                    ))}
                </div>
            </div>

            <div className="inspector-panel" style={{ flex: 1, marginLeft: '20px', borderLeft: '1px solid #ccc', paddingLeft: '20px', overflowY: 'auto' }}>
                <h3>UI Tree Inspector</h3>
                <div className="tree-content" style={{ fontSize: '12px', background: '#f4f4f4', padding: '10px', borderRadius: '4px' }}>
                    {uiTree ? <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(uiTree, null, 2)}</pre> : <p style={{ color: '#999' }}>Waiting for UI hierarchy data...</p>}
                </div>
            </div>
        </div>
    );
};

export default CanvasApp;
