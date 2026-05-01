/* Live2D MCP frontend patch — additions to Live2DViewer.jsx
 *
 * Apply phase merges this into the existing Live2DViewer.jsx component.
 * The patch adds:
 *  1. A WebSocket subscription to /ws/live2d/{conversationId}
 *  2. Motion + expression dispatch into the existing pixi-live2d-display model ref
 *  3. data-current-motion attribute on the canvas (read by Playwright eval)
 *
 * Yijun reviews the unified diff during apply phase before this lands.
 */

// === imports (add to top of Live2DViewer.jsx) ===
import { useEffect, useRef } from 'react';

// === inside the component body, after the existing model-mount useEffect ===

// Live2D MCP subscription — receives play_motion / set_expression events
// triggered server-side by LLM tool calls.
useEffect(() => {
  if (!conversationId) return;
  if (!modelRef.current || !canvasRef.current) return;

  const wsBase = (import.meta.env.VITE_WS_BASE || window.location.origin)
    .replace(/^http/, 'ws');
  const ws = new WebSocket(`${wsBase}/ws/live2d/${conversationId}`);

  ws.onmessage = (msg) => {
    let evt;
    try {
      evt = JSON.parse(msg.data);
    } catch {
      return;
    }
    if (evt.event === 'play_motion' && modelRef.current) {
      // pixi-live2d-display@0.4 motion API — name is the .mtn stem.
      modelRef.current.motion(evt.name);
      canvasRef.current.dataset.currentMotion = evt.name;
    } else if (evt.event === 'set_expression' && modelRef.current) {
      modelRef.current.expression(evt.name);
      canvasRef.current.dataset.currentExpression = evt.name;
      if (evt.hold_ms && evt.hold_ms < 10000) {
        setTimeout(() => {
          if (modelRef.current) modelRef.current.expression('f01');
        }, evt.hold_ms);
      }
    }
  };

  ws.onclose = () => {
    // Connection drops are normal on conversation switch — no UI surfacing.
  };

  return () => {
    if (ws.readyState === WebSocket.OPEN) ws.close();
  };
}, [conversationId]);

// === ensure canvasRef is set on the <canvas> element ===
// <canvas
//   ref={canvasRef}
//   data-current-motion="idle_00"
//   data-current-expression="f01"
//   ...
// />
