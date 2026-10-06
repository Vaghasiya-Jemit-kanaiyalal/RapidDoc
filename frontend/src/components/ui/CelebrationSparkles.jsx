import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export const CelebrationSparkles = ({ 
  title = "Welcome to RapidDoc!", 
  subtitle = "Your intelligent document workspace is ready.", 
  duration = 4200,
  onComplete 
}) => {
  const canvasRef = useRef(null);
  const [showToast, setShowToast] = useState(true);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animationFrameId;

    const resize = () => {
      if (!canvas) return;
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    // Festive popper colors (clean, bright, high-contrast)
    const colors = [
      '#365CFF', // RapidDoc Blue
      '#38BDF8', // Cyan
      '#6366F1', // Indigo
      '#A855F7', // Purple
      '#EC4899', // Pink
      '#F59E0B', // Gold Amber
      '#10B981', // Mint Green
      '#F43F5E', // Rose
    ];

    // High performance lightweight particle
    class PopperParticle {
      constructor(originX, originY, angleBase, angleSpread, speedMin, speedMax) {
        this.x = originX;
        this.y = originY;
        
        const angle = angleBase + (Math.random() - 0.5) * angleSpread;
        const speed = Math.random() * (speedMax - speedMin) + speedMin;
        
        this.vx = Math.cos(angle) * speed;
        this.vy = Math.sin(angle) * speed;
        
        this.gravity = 0.28;
        this.friction = 0.98;
        this.opacity = 1;
        this.decay = Math.random() * 0.009 + 0.007;
        
        this.color = colors[Math.floor(Math.random() * colors.length)];
        this.size = Math.random() * 7 + 4;
        
        // Shape: ribbon confetti or circular spark
        this.isRibbon = Math.random() > 0.35;
        this.rotation = Math.random() * 360;
        this.rotSpeed = (Math.random() - 0.5) * 10;
        this.wobble = Math.random() * Math.PI * 2;
        this.wobbleSpeed = Math.random() * 0.12 + 0.04;
      }

      update() {
        this.vx *= this.friction;
        this.vy = this.vy * this.friction + this.gravity;
        
        this.x += this.vx + Math.sin(this.wobble) * 1.1;
        this.y += this.vy;
        
        this.wobble += this.wobbleSpeed;
        this.rotation += this.rotSpeed;
        this.opacity -= this.decay;
      }

      draw(ctx) {
        if (this.opacity <= 0) return;
        ctx.save();
        ctx.translate(this.x, this.y);
        ctx.rotate((this.rotation * Math.PI) / 180);
        ctx.globalAlpha = Math.max(0, this.opacity);
        ctx.fillStyle = this.color;

        if (this.isRibbon) {
          // 3D Flipping Confetti Ribbon
          const w = this.size * Math.cos(this.wobble);
          const h = this.size * 1.5;
          ctx.fillRect(-w / 2, -h / 2, w, h);
        } else {
          // Circular / Star Sparkle
          ctx.beginPath();
          ctx.arc(0, 0, this.size * 0.6, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.restore();
      }
    }

    let particles = [];

    // Launch Crossing Poppers from bottom-left & bottom-right
    const firePoppers = (count = 80) => {
      const w = window.innerWidth;
      const h = window.innerHeight;

      // Left Cannon -> Shoots across towards top-right (-50 deg)
      const leftX = 20;
      const leftY = h * 0.92;
      for (let i = 0; i < count; i++) {
        particles.push(
          new PopperParticle(
            leftX,
            leftY,
            -Math.PI * 0.28, // -50 degrees
            Math.PI * 0.28,  // spread
            18,
            32
          )
        );
      }

      // Right Cannon -> Shoots across towards top-left (-130 deg)
      const rightX = w - 20;
      const rightY = h * 0.92;
      for (let i = 0; i < count; i++) {
        particles.push(
          new PopperParticle(
            rightX,
            rightY,
            -Math.PI * 0.72, // -130 degrees
            Math.PI * 0.28,  // spread
            18,
            32
          )
        );
      }
    };

    // Instant blast at t = 0
    firePoppers(75);

    // Follow-up burst at +220ms
    const followUpTimer = setTimeout(() => {
      firePoppers(50);
    }, 220);

    // 60FPS Render Loop
    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i];
        p.update();
        p.draw(ctx);
        if (p.opacity <= 0 || p.y > canvas.height + 60) {
          particles.splice(i, 1);
        }
      }

      if (particles.length > 0) {
        animationFrameId = requestAnimationFrame(render);
      }
    };

    render();

    // Auto-dismiss and complete
    const dismissTimer = setTimeout(() => {
      setShowToast(false);
      setTimeout(() => {
        if (onComplete) onComplete();
      }, 400);
    }, duration);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', resize);
      clearTimeout(followUpTimer);
      clearTimeout(dismissTimer);
    };
  }, [duration, onComplete]);

  return (
    <div className="pointer-events-none fixed inset-0 z-50 overflow-hidden select-none">
      
      {/* ── Lightweight 60FPS Canvas ── */}
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none z-10" />

      {/* ── Clean Celebration Banner (No AI symbols, Vercel optimized) ── */}
      <AnimatePresence>
        {showToast && (
          <motion.div
            initial={{ opacity: 0, y: -40, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -25, scale: 0.95 }}
            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className="absolute top-6 left-1/2 -translate-x-1/2 pointer-events-auto z-20 flex items-center gap-3 px-5 py-3 bg-white/95 backdrop-blur-md border border-slate-200/90 rounded-2xl shadow-[0_15px_40px_-10px_rgba(54,92,255,0.2),0_4px_12px_rgba(0,0,0,0.05)]"
          >
            <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-brand-50 border border-brand-100 text-lg shadow-2xs">
              🎉
            </div>

            <div className="text-left pr-1">
              <h4 className="text-sm font-extrabold text-slate-900 tracking-tight">
                {title}
              </h4>
              <p className="text-xs text-slate-500 font-medium">
                {subtitle}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  );
};

export default CelebrationSparkles;
