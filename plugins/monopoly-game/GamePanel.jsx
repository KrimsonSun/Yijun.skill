import { useEffect, useState } from 'react';
import './game.css';

const WS_BASE = (import.meta.env.VITE_WS_BASE || window.location.origin).replace(/^http/, 'ws');
const API_BASE = import.meta.env.VITE_API_BASE || '';

export function MonopolyPanel({ conversationId, onClose }) {
  const [state, setState] = useState(null);

  useEffect(() => {
    if (!conversationId) return;

    let cancelled = false;
    fetch(`${API_BASE}/games/monopoly/state?conversation_id=${conversationId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => { if (!cancelled && data) setState(data); });

    const ws = new WebSocket(`${WS_BASE}/ws/games/monopoly/${conversationId}`);
    ws.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data);
        if (evt.event === 'state') setState(evt.state);
      } catch {}
    };

    return () => {
      cancelled = true;
      if (ws.readyState === WebSocket.OPEN) ws.close();
    };
  }, [conversationId]);

  if (!state) {
    return (
      <div className="monopoly-panel monopoly-loading">
        <span>大富翁加载中…</span>
      </div>
    );
  }

  if (state.status === 'ended') {
    return (
      <div className="monopoly-panel">
        <div className="monopoly-header">
          <h3>{state.winner === 'emma' ? 'Emma 赢啦💕' : '你赢啦~ 贴贴'}</h3>
          <button className="monopoly-close" onClick={onClose}>×</button>
        </div>
      </div>
    );
  }

  return (
    <div className="monopoly-panel">
      <div className="monopoly-header">
        <h3>大富翁</h3>
        <button className="monopoly-close" onClick={onClose} aria-label="关闭">×</button>
      </div>
      <div className="monopoly-players">
        {state.players.map(p => (
          <div
            key={p.id}
            className={`monopoly-player ${state.turn === p.id ? 'is-turn' : ''}`}
          >
            <span className="monopoly-player-name">{p.display_name}</span>
            <span className="monopoly-player-money">${p.money}</span>
          </div>
        ))}
      </div>
      <div className="monopoly-board">
        {state.board.map((tile, idx) => {
          const playersHere = state.players.filter(p => p.position === idx);
          return (
            <div key={idx} className={`monopoly-tile monopoly-tile-${tile.type}`}>
              <span className="monopoly-tile-name">{tile.name}</span>
              {playersHere.length > 0 && (
                <span className="monopoly-tokens">
                  {playersHere.map(p => (p.id === 'emma' ? '💕' : '🐾')).join('')}
                </span>
              )}
            </div>
          );
        })}
      </div>
      {state.last_roll && (
        <div className="monopoly-last-roll">
          上次 {state.turn === 'user' ? 'Emma' : '你'} 掷出 {state.last_roll[0]} + {state.last_roll[1]}
        </div>
      )}
    </div>
  );
}
