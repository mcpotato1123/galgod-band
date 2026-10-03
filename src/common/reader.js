// 阅读器公共逻辑：设置项、存档读写、说话人配色
// 手环 9 Pro 只跑单页，这里的函数不做缓存，避免页面销毁后仍被全局引用

import storage from '@system.storage'

export const DEFAULT_SETTINGS = {
  speed: 28,            // 每个字的毫秒数；0 = 立即显示
  auto: false,          // 自动播放
  autoSpeed: 'medium'   // slow / medium / fast
}

const SPEED_PRESETS = { slow: 1.5, medium: 1, fast: 0.65 }
const AUTO_SPEEDS = { slow: 1.35, medium: 1, fast: 0.7 }

export const MAX_SLOTS = 6

// 说话人配色，让手环小屏上一眼能分清谁在说话
export const NAME_COLORS = {
  '陈舟': '#8fd3ff',
  '我': '#8fd3ff',
  '林曦': '#ff9ec4',
  '江晚晴': '#b9a2ff',
  '小涟': '#ffd166',
  '诺提拉': '#7ee8e0',
  '政客': '#ffb07c',
  '班主任': '#c9c9c9'
}

export function nameColor(name) {
  return NAME_COLORS[name] || '#ffe6ef'
}

export function normalizeSettings(raw) {
  const s = Object.assign({}, DEFAULT_SETTINGS, raw || {})
  if (typeof s.speed !== 'number' || !isFinite(s.speed) || s.speed < 0) s.speed = DEFAULT_SETTINGS.speed
  if (s.speed > 200) s.speed = 200
  if (!AUTO_SPEEDS[s.autoSpeed]) s.autoSpeed = 'medium'
  s.auto = !!s.auto
  return s
}

export function autoDelay(text, autoSpeed) {
  const n = String(text || '').replace(/\s/g, '').length
  const k = AUTO_SPEEDS[autoSpeed] || 1
  return Math.max(1500, Math.min(9000, Math.round((1100 + n * 70) * k)))
}

// ---------------------------------------------------------------- storage

export function readJSON(key, fallback, done) {
  storage.get({
    key: key,
    default: '',
    success: (v) => {
      if (!v) return done(fallback)
      try {
        done(JSON.parse(v))
      } catch (e) {
        done(fallback)
      }
    },
    fail: () => done(fallback)
  })
}

export function writeJSON(key, value, done) {
  storage.set({
    key: key,
    value: JSON.stringify(value),
    success: () => { if (done) done(true) },
    fail: () => { if (done) done(false) }
  })
}

export function loadSettings(done) {
  readJSON('settings', null, (v) => done(normalizeSettings(v)))
}

export function saveSettings(s, done) {
  writeJSON('settings', s, done)
}

export function loadSaves(done) {
  readJSON('saves', [], (v) => done(Array.isArray(v) ? v : []))
}

export function saveSaves(list, done) {
  writeJSON('saves', list, done)
}

export function loadAutoSave(done) {
  readJSON('autoSave', null, done)
}

export function saveAutoSave(data, done) {
  writeJSON('autoSave', data, done)
}

// ---------------------------------------------------------------- CG 鉴赏解锁记录
// 存的是「看过的 CG 图片下标」数组，对应原作里的 renpy.seen_image(...)
export function loadSeen(done) {
  readJSON('cgSeen', [], (v) => done(Array.isArray(v) ? v : []))
}

export function saveSeen(list, done) {
  writeJSON('cgSeen', list, done)
}

// ---------------------------------------------------------------- 通关记录
// 只有真结局才算通关；后日谈是通关奖励，通关前不出现在章节选择里
export function loadCleared(done) {
  readJSON('cleared', null, (v) => done(!!(v && v.ok)))
}

export function markCleared(done) {
  writeJSON('cleared', { ok: 1, at: Date.now() }, done)
}
