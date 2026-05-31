import { useEffect, useRef } from 'react'

// Self-contained WebGL "liquid glass" gradient mesh that reacts to cursor
// movement and clicks. Ported from the standalone Gradient Mesh Wallpaper
// design and adapted into a React component that cleans up after itself.
// The canvas paints a soft, near-white animated gradient with blue / lavender
// / peach accent blooms that mirror the Trip Architect palette.

const FRAG = `
  precision highp float;
  uniform vec2  u_res;
  uniform float u_time;
  uniform vec2  u_mouse;     // 0..1, y up
  uniform float u_speed;     // ambient motion rate
  uniform float u_warp;      // travel + cursor pull
  uniform float u_tint;      // colour strength
  uniform vec3  u_clicks[6]; // x,y,startTime  (z<0 inactive)

  const vec3 ACC_BLUE  = vec3(0.420, 0.722, 0.961);
  const vec3 ACC_PEACH = vec3(0.965, 0.780, 0.612);
  const vec3 ACC_LAV   = vec3(0.671, 0.694, 0.886);
  vec3 accent(float t){
    t = fract(t); float s = t * 3.0;
    if (s < 1.0)      return mix(ACC_BLUE,  ACC_LAV,   s);
    else if (s < 2.0) return mix(ACC_LAV,   ACC_PEACH, s - 1.0);
    else              return mix(ACC_PEACH, ACC_BLUE,  s - 2.0);
  }
  float hash21(vec2 p){
    p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32);
    return fract(p.x * p.y);
  }
  vec3 glassBase(vec2 uv){
    vec3 top = vec3(0.992, 0.994, 0.998);
    vec3 bot = vec3(0.945, 0.953, 0.965);
    return mix(bot, top, clamp(uv.y, 0.0, 1.0));
  }

  void main(){
    vec2 asp = vec2(u_res.x / u_res.y, 1.0);
    vec2 uv = gl_FragCoord.xy / u_res;
    vec2 p = uv * asp;
    vec2 m = u_mouse * asp;
    float t = u_time * u_speed;

    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int i = 0; i < 6; i++){
      float fi = float(i);
      vec2 base = vec2(0.5 + 0.42 * sin(t * 1.10 + fi * 1.3),
                       0.5 + 0.42 * cos(t * 0.90 + fi * 2.1));
      base *= asp;
      base += (m - base) * 0.22 * u_warp * (0.5 + 0.5 * sin(t * 1.7 + fi));
      float d = distance(p, base);
      float w = exp(-d * d * 8.5);
      acc += accent(fi * 0.16 + u_mouse.x * 0.45 + u_time * 0.02) * w;
      wsum += w;
    }
    // lingering click blooms that expand and fade
    for (int i = 0; i < 6; i++){
      vec3 ck = u_clicks[i];
      if (ck.z < 0.0) continue;
      float age = u_time - ck.z;
      float d = distance(p, ck.xy * asp);
      float k = 9.0 / (1.0 + age * 1.4);
      float w = exp(-d * d * k) * exp(-age * 0.40);
      acc += accent(age * 0.25 + u_mouse.x) * w * 1.7;
      wsum += w * 1.7;
    }
    acc /= max(wsum, 0.0001);

    vec3 col = glassBase(uv);
    float amt = clamp(wsum, 0.0, 1.0) * 0.34 * u_tint;
    col = mix(col, acc, amt);

    // glassy top sheen + faint cursor halo for liveliness
    col += pow(clamp(uv.y, 0.0, 1.0), 2.5) * 0.015;
    float dm = distance(p, m);
    col = mix(col, accent(u_mouse.x + 0.2), exp(-dm * 3.4) * 0.06 * u_tint);

    // dither to keep the soft gradient band-free on white
    col += (hash21(gl_FragCoord.xy + fract(u_time)) - 0.5) / 255.0;
    gl_FragColor = vec4(col, 1.0);
  }
`

const VERT = 'attribute vec2 a_pos; void main(){ gl_Position = vec4(a_pos,0.0,1.0); }'

// Locked to the calm "liquid glass" feel from the original design.
const CFG = { speed: 0.32, warp: 1.0, tint: 1.1 }

export default function ReactiveBackground() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined

    // No WebGL (e.g. test env or unsupported browser): leave the CSS gradient
    // fallback in place and do nothing. getContext can throw in some
    // environments (jsdom), so guard it.
    let gl = null
    try {
      gl = canvas.getContext('webgl', { antialias: false, alpha: false })
    } catch {
      gl = null
    }
    if (!gl) return undefined

    function compile(type, src) {
      const shader = gl.createShader(type)
      gl.shaderSource(shader, src)
      gl.compileShader(shader)
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error(gl.getShaderInfoLog(shader))
      }
      return shader
    }

    const prog = gl.createProgram()
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT))
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG))
    gl.linkProgram(prog)
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.error(gl.getProgramInfoLog(prog))
    }
    gl.useProgram(prog)

    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    const aPos = gl.getAttribLocation(prog, 'a_pos')
    gl.enableVertexAttribArray(aPos)
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0)

    const U = {}
    ;['u_res', 'u_time', 'u_mouse', 'u_speed', 'u_warp', 'u_tint', 'u_clicks'].forEach((name) => {
      U[name] = gl.getUniformLocation(prog, name)
    })

    const DPR_CAP = 1.5
    function resize() {
      const dpr = Math.min(DPR_CAP, window.devicePixelRatio || 1)
      const w = Math.round(window.innerWidth * dpr)
      const h = Math.round(window.innerHeight * dpr)
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w
        canvas.height = h
      }
    }
    resize()

    const state = { rawX: 0.5, rawY: 0.5, mouseX: 0.5, mouseY: 0.5, speed: 0, lastT: 0 }
    const MAX_CLICKS = 6
    const clicks = new Array(MAX_CLICKS).fill(null)
    let clickHead = 0
    const clickBuf = new Float32Array(18)

    const start = performance.now()
    const now = () => (performance.now() - start) / 1000

    function onMouseMove(e) {
      state.rawX = e.clientX / window.innerWidth
      state.rawY = 1 - e.clientY / window.innerHeight
    }
    function onTouchMove(e) {
      const tch = e.touches[0]
      if (!tch) return
      state.rawX = tch.clientX / window.innerWidth
      state.rawY = 1 - tch.clientY / window.innerHeight
    }
    function addClick(cx, cy) {
      clicks[clickHead] = { x: cx / window.innerWidth, y: 1 - cy / window.innerHeight, t: now() }
      clickHead = (clickHead + 1) % MAX_CLICKS
    }
    function onClick(e) {
      addClick(e.clientX, e.clientY)
    }
    function onTouchStart(e) {
      const tch = e.touches[0]
      if (tch) addClick(tch.clientX, tch.clientY)
    }

    window.addEventListener('resize', resize)
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('touchmove', onTouchMove, { passive: true })
    window.addEventListener('click', onClick)
    window.addEventListener('touchstart', onTouchStart, { passive: true })

    // speed-gated mouse follow: ease along when slow, freeze on fast flicks.
    const SLOW = 0.6
    const FAST = 3.0
    const MAX_RATE = 5.0
    let prevRawX = 0.5
    let prevRawY = 0.5
    function smoothstep(a, b, x) {
      const u = Math.min(1, Math.max(0, (x - a) / (b - a)))
      return u * u * (3 - 2 * u)
    }
    function updateFollow(t) {
      let dt = t - state.lastT
      state.lastT = t
      if (dt <= 0 || dt > 0.1) dt = 1 / 60

      const dx = state.rawX - state.mouseX
      const dy = state.rawY - state.mouseY
      const inst = Math.hypot(state.rawX - prevRawX, state.rawY - prevRawY) / dt
      prevRawX = state.rawX
      prevRawY = state.rawY
      const a = inst > state.speed ? 0.6 : 0.1
      state.speed += (inst - state.speed) * a

      const gate = 1 - smoothstep(SLOW, FAST, state.speed)
      const k = 1 - Math.exp(-MAX_RATE * gate * dt)
      state.mouseX += dx * k
      state.mouseY += dy * k
    }

    let frame = 0
    function loop() {
      const t = now()
      updateFollow(t)
      gl.viewport(0, 0, canvas.width, canvas.height)
      gl.uniform2f(U.u_res, canvas.width, canvas.height)
      gl.uniform1f(U.u_time, t)
      gl.uniform2f(U.u_mouse, state.mouseX, state.mouseY)
      gl.uniform1f(U.u_speed, CFG.speed)
      gl.uniform1f(U.u_warp, CFG.warp)
      gl.uniform1f(U.u_tint, CFG.tint)
      for (let i = 0; i < MAX_CLICKS; i++) {
        const c = clicks[i]
        clickBuf[i * 3] = c ? c.x : 0
        clickBuf[i * 3 + 1] = c ? c.y : 0
        clickBuf[i * 3 + 2] = c ? c.t : -1
      }
      gl.uniform3fv(U.u_clicks, clickBuf)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
      frame = requestAnimationFrame(loop)
    }
    frame = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', resize)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('touchmove', onTouchMove)
      window.removeEventListener('click', onClick)
      window.removeEventListener('touchstart', onTouchStart)
      const lose = gl.getExtension('WEBGL_lose_context')
      if (lose) lose.loseContext()
    }
  }, [])

  return <canvas aria-hidden="true" className="reactive-bg" ref={canvasRef} />
}
