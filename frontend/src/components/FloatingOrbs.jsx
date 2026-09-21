import { useEffect, useRef } from 'react';

/**
 * FloatingOrbs — Upward-motion dynamic morphing canvas background for all lower landing page sections.
 * 
 * Features:
 *  - Spans across all content sections (Features, How It Works, AI Engine, Testimonials, CTA, Footer)
 *  - Continuous upward floating drift with smooth 3D flipping (RapidDoc -> Word -> PDF)
 *  - Crisp light-border outlines with clean white interior
 *  - 360° rotating AI sparkles & stars
 *  - Interactive mouse repulsion
 */
const FloatingOrbs = ({ className = '' }) => {
  const canvasRef = useRef(null);
  const animationRef = useRef(null);
  const mouseRef = useRef({ x: -1000, y: -1000, targetX: -1000, targetY: -1000 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    const resize = () => {
      const parent = canvas.parentElement;
      const width = parent ? parent.clientWidth : window.innerWidth;
      const height = parent ? parent.clientHeight : window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(dpr, dpr);
    };

    resize();
    window.addEventListener('resize', resize);

    const handleMouseMove = (e) => {
      const rect = canvas.getBoundingClientRect();
      mouseRef.current.targetX = e.clientX - rect.left;
      mouseRef.current.targetY = e.clientY - rect.top;
    };

    const handleMouseLeave = () => {
      mouseRef.current.targetX = -1000;
      mouseRef.current.targetY = -1000;
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseleave', handleMouseLeave);

    // States for morphing icons: 0: RapidDoc (AI), 1: Word (DOCX), 2: PDF
    const STATES = [
      {
        id: 'rapiddoc',
        name: 'RapidDoc',
        tag: 'AI ✦',
        borderColor: '#8B5CF6',      // Purple
        glowColor: 'rgba(139, 92, 246, 0.4)',
        textColor: '#7C3AED',
        bgFill: 'rgba(255, 255, 255, 0.94)',
      },
      {
        id: 'word',
        name: 'Word',
        tag: 'W',
        borderColor: '#3B82F6',      // Light Blue
        glowColor: 'rgba(59, 130, 246, 0.4)',
        textColor: '#2563EB',
        bgFill: 'rgba(255, 255, 255, 0.94)',
      },
      {
        id: 'pdf',
        name: 'PDF',
        tag: 'PDF',
        borderColor: '#EF4444',      // Light Red
        glowColor: 'rgba(239, 68, 68, 0.4)',
        textColor: '#DC2626',
        bgFill: 'rgba(255, 255, 255, 0.94)',
      },
    ];

    // Morphing Document Nodes distributed down the full content height (Increased count)
    const morphingNodes = [
      { xFrac: 0.07, yFrac: 0.03, w: 52, h: 64, speedY: 0.85, waveAmp: 25, waveSpeed: 0.02, phase: 0.5, currentState: 0, flipProgress: 0, flipSpeed: 0.022, distSinceLastFlip: 0, nextFlipDistance: 140 },
      { xFrac: 0.92, yFrac: 0.08, w: 54, h: 66, speedY: 0.95, waveAmp: 30, waveSpeed: 0.018, phase: 1.8, currentState: 1, flipProgress: 0, flipSpeed: 0.02, distSinceLastFlip: 50, nextFlipDistance: 160 },
      { xFrac: 0.15, yFrac: 0.15, w: 50, h: 62, speedY: 0.80, waveAmp: 22, waveSpeed: 0.022, phase: 3.2, currentState: 2, flipProgress: 0, flipSpeed: 0.024, distSinceLastFlip: 100, nextFlipDistance: 150 },
      { xFrac: 0.85, yFrac: 0.20, w: 52, h: 64, speedY: 0.90, waveAmp: 24, waveSpeed: 0.019, phase: 4.5, currentState: 0, flipProgress: 0, flipSpeed: 0.021, distSinceLastFlip: 30, nextFlipDistance: 170 },
      { xFrac: 0.48, yFrac: 0.26, w: 48, h: 60, speedY: 0.88, waveAmp: 28, waveSpeed: 0.021, phase: 2.4, currentState: 1, flipProgress: 0, flipSpeed: 0.023, distSinceLastFlip: 80, nextFlipDistance: 155 },
      { xFrac: 0.09, yFrac: 0.32, w: 50, h: 62, speedY: 0.92, waveAmp: 24, waveSpeed: 0.017, phase: 5.1, currentState: 2, flipProgress: 0, flipSpeed: 0.025, distSinceLastFlip: 120, nextFlipDistance: 165 },
      { xFrac: 0.90, yFrac: 0.38, w: 52, h: 64, speedY: 0.86, waveAmp: 26, waveSpeed: 0.02, phase: 1.2, currentState: 0, flipProgress: 0, flipSpeed: 0.022, distSinceLastFlip: 40, nextFlipDistance: 150 },
      { xFrac: 0.22, yFrac: 0.44, w: 54, h: 66, speedY: 0.94, waveAmp: 28, waveSpeed: 0.018, phase: 3.8, currentState: 1, flipProgress: 0, flipSpeed: 0.021, distSinceLastFlip: 70, nextFlipDistance: 160 },
      { xFrac: 0.78, yFrac: 0.50, w: 50, h: 62, speedY: 0.82, waveAmp: 22, waveSpeed: 0.022, phase: 2.1, currentState: 2, flipProgress: 0, flipSpeed: 0.023, distSinceLastFlip: 90, nextFlipDistance: 155 },
      { xFrac: 0.52, yFrac: 0.56, w: 52, h: 64, speedY: 0.90, waveAmp: 25, waveSpeed: 0.019, phase: 4.2, currentState: 0, flipProgress: 0, flipSpeed: 0.022, distSinceLastFlip: 20, nextFlipDistance: 170 },
      { xFrac: 0.12, yFrac: 0.62, w: 48, h: 60, speedY: 0.88, waveAmp: 26, waveSpeed: 0.021, phase: 0.7, currentState: 1, flipProgress: 0, flipSpeed: 0.024, distSinceLastFlip: 60, nextFlipDistance: 145 },
      { xFrac: 0.88, yFrac: 0.68, w: 50, h: 62, speedY: 0.92, waveAmp: 24, waveSpeed: 0.018, phase: 2.9, currentState: 2, flipProgress: 0, flipSpeed: 0.022, distSinceLastFlip: 85, nextFlipDistance: 160 },
      { xFrac: 0.30, yFrac: 0.74, w: 52, h: 64, speedY: 0.86, waveAmp: 27, waveSpeed: 0.02, phase: 4.7, currentState: 0, flipProgress: 0, flipSpeed: 0.021, distSinceLastFlip: 35, nextFlipDistance: 150 },
      { xFrac: 0.72, yFrac: 0.80, w: 54, h: 66, speedY: 0.95, waveAmp: 29, waveSpeed: 0.019, phase: 1.5, currentState: 1, flipProgress: 0, flipSpeed: 0.023, distSinceLastFlip: 75, nextFlipDistance: 165 },
      { xFrac: 0.14, yFrac: 0.86, w: 50, h: 62, speedY: 0.84, waveAmp: 23, waveSpeed: 0.021, phase: 3.4, currentState: 2, flipProgress: 0, flipSpeed: 0.024, distSinceLastFlip: 110, nextFlipDistance: 155 },
      { xFrac: 0.86, yFrac: 0.92, w: 52, h: 64, speedY: 0.89, waveAmp: 25, waveSpeed: 0.018, phase: 5.3, currentState: 0, flipProgress: 0, flipSpeed: 0.022, distSinceLastFlip: 25, nextFlipDistance: 170 },
      { xFrac: 0.45, yFrac: 0.97, w: 48, h: 60, speedY: 0.91, waveAmp: 26, waveSpeed: 0.022, phase: 2.0, currentState: 1, flipProgress: 0, flipSpeed: 0.025, distSinceLastFlip: 65, nextFlipDistance: 145 },
    ];

    // Rotating AI Sparkles and Stars distributed across the full content height (Increased count)
    const risingSparkles = [
      { xFrac: 0.04, yFrac: 0.05, r: 16, color: '#8B5CF6', glow: 'rgba(139,92,246,0.4)', speedY: 1.1, rotSpeed: 0.035, phase: 0.3, type: 'sparkle' },
      { xFrac: 0.95, yFrac: 0.10, r: 18, color: '#3B82F6', glow: 'rgba(59,130,246,0.4)', speedY: 1.0, rotSpeed: -0.032, phase: 2.1, type: 'sparkle' },
      { xFrac: 0.28, yFrac: 0.14, r: 13, color: '#F59E0B', glow: 'rgba(245,158,11,0.4)', speedY: 1.05, rotSpeed: 0.036, phase: 1.1, type: 'star' },
      { xFrac: 0.72, yFrac: 0.18, r: 15, color: '#EC4899', glow: 'rgba(236,72,153,0.35)', speedY: 1.12, rotSpeed: -0.038, phase: 3.5, type: 'sparkle' },
      { xFrac: 0.12, yFrac: 0.23, r: 14, color: '#EF4444', glow: 'rgba(239,68,68,0.35)', speedY: 1.2, rotSpeed: 0.038, phase: 1.4, type: 'sparkle' },
      { xFrac: 0.88, yFrac: 0.28, r: 15, color: '#F59E0B', glow: 'rgba(245,158,11,0.4)', speedY: 0.95, rotSpeed: -0.034, phase: 3.7, type: 'star' },
      { xFrac: 0.40, yFrac: 0.33, r: 13, color: '#10B981', glow: 'rgba(16,185,129,0.35)', speedY: 1.15, rotSpeed: 0.04, phase: 4.8, type: 'sparkle' },
      { xFrac: 0.62, yFrac: 0.39, r: 14, color: '#8B5CF6', glow: 'rgba(139,92,246,0.35)', speedY: 1.05, rotSpeed: -0.036, phase: 0.9, type: 'star' },
      { xFrac: 0.06, yFrac: 0.45, r: 12, color: '#38BDF8', glow: 'rgba(56,189,248,0.35)', speedY: 1.08, rotSpeed: 0.032, phase: 2.8, type: 'sparkle' },
      { xFrac: 0.94, yFrac: 0.51, r: 15, color: '#EC4899', glow: 'rgba(236,72,153,0.35)', speedY: 1.12, rotSpeed: -0.038, phase: 5.4, type: 'sparkle' },
      { xFrac: 0.25, yFrac: 0.57, r: 14, color: '#F59E0B', glow: 'rgba(245,158,11,0.4)', speedY: 1.0, rotSpeed: 0.034, phase: 1.7, type: 'star' },
      { xFrac: 0.76, yFrac: 0.63, r: 16, color: '#8B5CF6', glow: 'rgba(139,92,246,0.4)', speedY: 1.1, rotSpeed: -0.036, phase: 3.1, type: 'sparkle' },
      { xFrac: 0.38, yFrac: 0.69, r: 13, color: '#3B82F6', glow: 'rgba(59,130,246,0.35)', speedY: 1.05, rotSpeed: 0.038, phase: 4.5, type: 'sparkle' },
      { xFrac: 0.10, yFrac: 0.75, r: 15, color: '#10B981', glow: 'rgba(16,185,129,0.35)', speedY: 1.14, rotSpeed: 0.036, phase: 0.8, type: 'sparkle' },
      { xFrac: 0.90, yFrac: 0.81, r: 14, color: '#EF4444', glow: 'rgba(239,68,68,0.35)', speedY: 1.08, rotSpeed: -0.032, phase: 2.6, type: 'star' },
      { xFrac: 0.55, yFrac: 0.87, r: 15, color: '#8B5CF6', glow: 'rgba(139,92,246,0.4)', speedY: 1.1, rotSpeed: 0.035, phase: 4.1, type: 'sparkle' },
      { xFrac: 0.18, yFrac: 0.93, r: 13, color: '#38BDF8', glow: 'rgba(56,189,248,0.35)', speedY: 1.06, rotSpeed: -0.034, phase: 1.3, type: 'star' },
      { xFrac: 0.82, yFrac: 0.98, r: 16, color: '#F59E0B', glow: 'rgba(245,158,11,0.4)', speedY: 1.12, rotSpeed: 0.038, phase: 3.9, type: 'sparkle' },
    ];

    // Helper: Draw curved 4-pointed AI sparkle
    const drawAiSparkle = (cx, cy, r, color, glow, angle) => {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(angle);

      const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, r * 2.2);
      grad.addColorStop(0, glow);
      grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(0, 0, r * 2.2, 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      for (let i = 0; i < 4; i++) {
        const a = (i * Math.PI) / 2;
        const nextA = ((i + 1) * Math.PI) / 2;
        const midA = a + Math.PI / 4;
        const innerR = r * 0.26;

        if (i === 0) ctx.moveTo(Math.cos(a) * r, Math.sin(a) * r);
        ctx.quadraticCurveTo(
          Math.cos(midA) * innerR,
          Math.sin(midA) * innerR,
          Math.cos(nextA) * r,
          Math.sin(nextA) * r
        );
      }
      ctx.closePath();
      ctx.fillStyle = 'rgba(255, 255, 255, 0.94)';
      ctx.fill();

      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4;
      ctx.shadowColor = glow;
      ctx.shadowBlur = 8;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(0, 0, 2.2, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      ctx.restore();
    };

    // Helper: Draw 5-pointed star
    const draw5PointStar = (cx, cy, r, color, glow, angle) => {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(angle);

      const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, r * 1.9);
      grad.addColorStop(0, glow);
      grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(0, 0, r * 1.9, 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      for (let i = 0; i < 5; i++) {
        const outerA = (i * Math.PI * 2) / 5 - Math.PI / 2;
        const innerA = outerA + Math.PI / 5;
        const ox = Math.cos(outerA) * r;
        const oy = Math.sin(outerA) * r;
        const ix = Math.cos(innerA) * (r * 0.44);
        const iy = Math.sin(innerA) * (r * 0.44);

        if (i === 0) ctx.moveTo(ox, oy);
        else ctx.lineTo(ox, oy);
        ctx.lineTo(ix, iy);
      }
      ctx.closePath();
      ctx.fillStyle = 'rgba(255, 255, 255, 0.94)';
      ctx.fill();

      ctx.strokeStyle = color;
      ctx.lineWidth = 1.3;
      ctx.shadowColor = glow;
      ctx.shadowBlur = 8;
      ctx.stroke();

      ctx.restore();
    };

    // Helper: Draw Morphing Document Card
    const drawMorphingDoc = (cx, cy, w, h, stateObj, flipScaleX, wobbleAngle) => {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(wobbleAngle);
      ctx.scale(flipScaleX, 1);

      const x = -w / 2;
      const y = -h / 2;
      const corner = 8;
      const fold = 12;

      const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, Math.max(w, h) * 0.9);
      grad.addColorStop(0, stateObj.glowColor);
      grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(0, 0, Math.max(w, h) * 0.9, 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      ctx.moveTo(x + corner, y);
      ctx.lineTo(x + w - fold, y);
      ctx.lineTo(x + w, y + fold);
      ctx.lineTo(x + w, y + h - corner);
      ctx.quadraticCurveTo(x + w, y + h, x + w - corner, y + h);
      ctx.lineTo(x + corner, y + h);
      ctx.quadraticCurveTo(x, y + h, x, y + h - corner);
      ctx.lineTo(x, y + corner);
      ctx.quadraticCurveTo(x, y, x + corner, y);
      ctx.closePath();

      ctx.fillStyle = stateObj.bgFill;
      ctx.fill();

      ctx.strokeStyle = stateObj.borderColor;
      ctx.lineWidth = 1.4;
      ctx.shadowColor = stateObj.glowColor;
      ctx.shadowBlur = 8;
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(x + w - fold, y);
      ctx.lineTo(x + w - fold, y + fold);
      ctx.lineTo(x + w, y + fold);
      ctx.closePath();
      ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
      ctx.fill();
      ctx.strokeStyle = stateObj.borderColor;
      ctx.lineWidth = 1.2;
      ctx.stroke();

      if (stateObj.id === 'word') {
        const badgeW = 20;
        const badgeH = 20;
        const bx = x + 8;
        const by = y + 10;

        ctx.beginPath();
        ctx.roundRect(bx, by, badgeW, badgeH, 4);
        ctx.fillStyle = stateObj.borderColor;
        ctx.fill();

        ctx.font = 'bold 12px Inter, system-ui, sans-serif';
        ctx.fillStyle = '#FFFFFF';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('W', bx + badgeW / 2, by + badgeH / 2 + 0.5);

        ctx.fillStyle = 'rgba(59, 130, 246, 0.25)';
        ctx.fillRect(bx + badgeW + 6, by + 4, w - badgeW - 22, 2);
        ctx.fillRect(bx + badgeW + 6, by + 10, w - badgeW - 26, 2);

        ctx.fillStyle = 'rgba(100, 116, 139, 0.25)';
        ctx.fillRect(x + 8, y + 36, w - 16, 2);
        ctx.fillRect(x + 8, y + 43, w - 22, 2);
        ctx.fillRect(x + 8, y + 50, w - 28, 2);

      } else if (stateObj.id === 'pdf') {
        const badgeW = 26;
        const badgeH = 16;
        const bx = x + (w - badgeW) / 2;
        const by = y + 12;

        ctx.beginPath();
        ctx.roundRect(bx, by, badgeW, badgeH, 3);
        ctx.fillStyle = stateObj.borderColor;
        ctx.fill();

        ctx.font = 'bold 9px Inter, system-ui, sans-serif';
        ctx.fillStyle = '#FFFFFF';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('PDF', bx + badgeW / 2, by + badgeH / 2 + 0.5);

        ctx.fillStyle = 'rgba(239, 68, 68, 0.25)';
        ctx.fillRect(x + 8, y + 36, w - 16, 2);
        ctx.fillRect(x + 8, y + 43, w - 20, 2);
        ctx.fillRect(x + 8, y + 50, w - 26, 2);

      } else {
        const badgeW = 32;
        const badgeH = 17;
        const bx = x + (w - badgeW) / 2;
        const by = y + 12;

        ctx.beginPath();
        ctx.roundRect(bx, by, badgeW, badgeH, 8);
        ctx.fillStyle = 'rgba(139, 92, 246, 0.12)';
        ctx.fill();
        ctx.strokeStyle = stateObj.borderColor;
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.font = 'bold 9px Inter, system-ui, sans-serif';
        ctx.fillStyle = stateObj.textColor;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('AI ✦', bx + badgeW / 2, by + badgeH / 2 + 0.5);

        ctx.fillStyle = 'rgba(139, 92, 246, 0.25)';
        ctx.fillRect(x + 8, y + 36, w - 16, 2);
        ctx.fillRect(x + 8, y + 43, w - 22, 2);
        ctx.fillRect(x + 8, y + 50, w - 18, 2);
      }

      ctx.restore();
    };

    let time = 0;

    const draw = () => {
      const parent = canvas.parentElement;
      const w = parent ? parent.offsetWidth : window.innerWidth;
      const h = parent ? parent.offsetHeight : window.innerHeight;

      ctx.clearRect(0, 0, w, h);

      // Smooth mouse follow
      mouseRef.current.x += (mouseRef.current.targetX - mouseRef.current.x) * 0.05;
      mouseRef.current.y += (mouseRef.current.targetY - mouseRef.current.y) * 0.05;

      // 1. Rising Rotating AI Sparkles
      risingSparkles.forEach((sp) => {
        sp.yFrac -= (sp.speedY / h);

        if (sp.yFrac * h < -60) {
          sp.yFrac = 1.02;
          sp.xFrac = 0.04 + Math.random() * 0.92;
        }

        let sx = sp.xFrac * w + Math.sin(time * 0.02 + sp.phase) * 20;
        let sy = sp.yFrac * h;

        if (mouseRef.current.x > 0 && mouseRef.current.y > 0) {
          const dx = sx - mouseRef.current.x;
          const dy = sy - mouseRef.current.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 160 && dist > 0) {
            const force = (1 - dist / 160) * 22;
            sx += (dx / dist) * force;
            sy += (dy / dist) * force;
          }
        }

        const rotAngle = time * sp.rotSpeed + sp.phase;
        if (sp.type === 'sparkle') {
          drawAiSparkle(sx, sy, sp.r, sp.color, sp.glow, rotAngle);
        } else {
          draw5PointStar(sx, sy, sp.r, sp.color, sp.glow, rotAngle);
        }
      });

      // 2. Morphing Document Icons (Slide up continuously + 3D Flip State Cycle)
      morphingNodes.forEach((node) => {
        node.yFrac -= (node.speedY / h);
        node.distSinceLastFlip += node.speedY;

        if (node.yFrac * h < -80) {
          node.yFrac = 1.03;
          node.xFrac = 0.06 + Math.random() * 0.88;
        }

        if (node.distSinceLastFlip >= node.nextFlipDistance && node.flipProgress === 0) {
          node.flipProgress = 0.001;
          node.distSinceLastFlip = 0;
        }

        let flipScaleX = 1;

        if (node.flipProgress > 0) {
          node.flipProgress += node.flipSpeed;
          flipScaleX = Math.cos(node.flipProgress * Math.PI);

          if (node.flipProgress >= 0.5 && !node.hasSwitched) {
            node.currentState = (node.currentState + 1) % STATES.length;
            node.hasSwitched = true;
          }

          if (node.flipProgress >= 1.0) {
            node.flipProgress = 0;
            node.hasSwitched = false;
            node.nextFlipDistance = 140 + Math.random() * 80;
            flipScaleX = 1;
          }
        }

        let nx = node.xFrac * w + Math.sin(time * node.waveSpeed + node.phase) * node.waveAmp;
        let ny = node.yFrac * h;
        const wobbleAngle = Math.sin(time * 0.02 + node.phase) * 0.14;

        if (mouseRef.current.x > 0 && mouseRef.current.y > 0) {
          const dx = nx - mouseRef.current.x;
          const dy = ny - mouseRef.current.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 200 && dist > 0) {
            const force = (1 - dist / 200) * 30;
            nx += (dx / dist) * force;
            ny += (dy / dist) * force;
          }
        }

        const stateObj = STATES[node.currentState];
        drawMorphingDoc(nx, ny, node.w, node.h, stateObj, Math.abs(flipScaleX), wobbleAngle);
      });

      time += 1;
      animationRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseleave', handleMouseLeave);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 w-full h-full pointer-events-none block ${className}`}
      aria-hidden="true"
      style={{ mixBlendMode: 'normal' }}
    />
  );
};

export default FloatingOrbs;
