/**
 * Promptx Studio - Professional Manual Editing Suite
 * Handles direct manipulation, visual trimming, advanced styling, canvas ratios, 
 * keyframe animations, and professional cinematic presets.
 */

class ManualEditor {
    constructor() {
        this.video = document.getElementById('manualVideo');
        this.section = document.getElementById('manualEditorSection');
        this.seek = document.getElementById('manualSeek');
        this.currentTimeText = document.getElementById('currentTime');
        this.durationTimeText = document.getElementById('durationTime');
        this.playPauseBtn = document.getElementById('playPauseBtn');
        this.restartBtn = document.getElementById('restartBtn');
        this.exportBtn = document.getElementById('exportManualBtn');
        this.manualUpload = document.getElementById('manualVideoUpload');
        this.statusText = document.getElementById('manualStatus');
        
        // Trimmer
        this.trimTrack = document.getElementById('trimTrack');
        this.trimRegion = document.getElementById('trimRegion');
        this.leftHandle = document.getElementById('leftHandle');
        this.rightHandle = document.getElementById('rightHandle');
        this.valTrimStart = document.getElementById('valTrimStart');
        this.valTrimEnd = document.getElementById('valTrimEnd');
        this.keyframeTrack = document.getElementById('keyframeTrack');

        // Adjustments & Video Effects
        this.adjSliders = document.querySelectorAll('.adj-slider');
        this.speedSlider = document.getElementById('speedSlider');
        this.speedVal = document.getElementById('speedVal');
        this.ratioBtns = document.querySelectorAll('.ratio-btn');
        this.kfButtons = document.querySelectorAll('.kf-btn');
        this.videoMotion = document.getElementById('videoMotion');
        this.videoOverlay = document.getElementById('videoOverlay');
        this.videoTransition = document.getElementById('videoTransition');

        // Text
        this.textContentInput = document.getElementById('manualTextContent');
        this.addTextBtn = document.getElementById('addTextBtn');
        this.textListContainer = document.getElementById('activeTextList');
        this.textOverlayContainer = document.getElementById('textOverlayContainer');
        this.stylingControls = document.getElementById('textStylingControls');
        this.animationControls = document.getElementById('textAnimationControls');
        this.textFont = document.getElementById('textFont');
        this.textColor = document.getElementById('textColor');
        this.textBgToggle = document.getElementById('textBgToggle');
        this.textTabs = document.querySelectorAll('#textTabs .tab-btn');
        
        // Text Animation Dropdowns
        this.animIn = document.getElementById('animIn');
        this.animOut = document.getElementById('animOut');
        this.animLoop = document.getElementById('animLoop');
        this.animDur = document.getElementById('animDur');

        // State
        this.isInitialized = false;
        this.state = {
            videoUrl: '',
            sourceFile: null,
            speed: 1.0,
            trimStart: 0,
            trimEndIdx: 0,
            ratio: 'original',
            adjustments: { 
                brightness: 100, contrast: 100, saturate: 100, sepia: 0, grayscale: 0,
                keyframes: {} 
            },
            videoEffects: { 
                motion: 'none', 
                overlay: 'none', 
                transition: 'none' 
            },
            textOverlays: [],
            activeTextId: null
        };

        this.dragging = null;
        this.dragStartData = null;
        this.initEvents();
    }

    init(videoUrl, sourceFile = null) {
        if (!videoUrl) return;
        this.state.videoUrl = videoUrl;
        this.state.sourceFile = sourceFile;
        this.video.src = videoUrl;
        this.isInitialized = true;
        const container = document.getElementById('manualVideoContainer');
        if (container) container.classList.add('has-video');
        const placeholder = document.getElementById('videoPlaceholder');
        if (placeholder) placeholder.style.display = 'none';

        this.video.onloadedmetadata = () => {
            const vw = this.video.videoWidth, vh = this.video.videoHeight;
            const container = document.getElementById('manualVideoContainer');
            if (this.state.ratio === 'original' && vw && vh) container.style.aspectRatio = `${vw} / ${vh}`;
            this.durationTimeText.innerText = this.formatTime(this.video.duration);
            this.seek.max = this.video.duration;
            this.state.trimEndIdx = this.video.duration;
            this.updateTrimVisuals();
        };
        this.section.scrollIntoView({ behavior: 'smooth' });
    }

    initEvents() {
        if (this.manualUpload) {
            this.manualUpload.onchange = (e) => {
                const file = e.target.files[0];
                if (file) this.init(URL.createObjectURL(file), file);
            };
        }

        this.playPauseBtn.onclick = () => this.togglePlay();
        this.restartBtn.onclick = () => { this.video.currentTime = this.state.trimStart; this.video.play(); };

        this.video.ontimeupdate = () => {
            this.seek.value = this.video.currentTime;
            this.currentTimeText.innerText = this.formatTime(this.video.currentTime);
            this.updateTimelineProgress();
            this.checkTrimBounds();
            this.applyDynamicKeyframes(); 
        };

        this.seek.oninput = () => { this.video.currentTime = this.seek.value; this.applyDynamicKeyframes(); };

        this.adjSliders.forEach(slider => {
            slider.oninput = () => {
                const prop = slider.dataset.filter;
                this.state.adjustments[prop] = slider.value;
                this.recordKeyframe(prop, slider.value);
                this.applyFilters();
            };
        });

        this.kfButtons.forEach(btn => {
            btn.onclick = () => this.toggleKeyframe(btn.dataset.prop);
        });

        // Video Master Effects Events
        ['videoMotion', 'videoOverlay', 'videoTransition'].forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.onchange = () => {
                    const prop = id.replace('video', '').toLowerCase();
                    this.state.videoEffects[prop] = el.value;
                    this.applyVideoPreviewEffects();
                };
            }
        });

        if (this.speedSlider) {
            this.speedSlider.oninput = () => {
                const speed = parseFloat(this.speedSlider.value);
                this.state.speed = speed;
                this.video.playbackRate = speed;
                this.speedVal.innerText = speed.toFixed(1);
            };
        }

        this.ratioBtns.forEach(btn => { btn.onclick = () => this.setRatio(btn.dataset.ratio); });

        this.leftHandle.onmousedown = (e) => this.startDragging(e, 'left');
        this.rightHandle.onmousedown = (e) => this.startDragging(e, 'right');
        window.onmousemove = (e) => this.handleDragging(e);
        window.onmouseup = () => this.stopDragging();

        this.textOverlayContainer.onmousedown = (e) => { if (e.target === this.textOverlayContainer) this.selectText(null); };
        
        // Style Tab Events
        this.textFont.onchange = () => this.updateActiveTextStyles();
        this.textColor.oninput = () => this.updateActiveTextStyles();
        this.textBgToggle.onchange = () => this.updateActiveTextStyles();
        
        // Animation Tab Events
        [this.animIn, this.animOut, this.animLoop, this.animDur].forEach(el => {
            if (el) el.onchange = () => this.updateActiveTextAnimations();
        });

        this.textTabs.forEach(tab => {
           tab.onclick = () => {
              this.textTabs.forEach(t => t.classList.remove('active'));
              tab.classList.add('active');
              const isStyle = tab.dataset.tab === 'style';
              this.stylingControls.style.display = isStyle ? 'block' : 'none';
              this.animationControls.style.display = isStyle ? 'none' : 'block';
           };
        });

        this.addTextBtn.onclick = () => this.addTextOverlay();
        this.exportBtn.onclick = () => this.handleExport();
    }

    applyVideoPreviewEffects() {
        const effects = this.state.videoEffects;
        const container = document.getElementById('manualVideoContainer');
        if (!container) return;

        // Reset
        container.classList.remove('vfx-vhs', 'vfx-glitch', 'vfx-grain');
        if (effects.overlay !== 'none') container.classList.add(`vfx-${effects.overlay}`);
        
        // Basic CSS for transitions
        this.video.style.transition = 'opacity 0.5s';
        if (effects.transition === 'fade-in' && this.video.currentTime < 1) this.video.style.opacity = '0';
        else this.video.style.opacity = '1';
    }

    toggleKeyframe(prop) {
        if (!this.isInitialized) return;
        const time = parseFloat(this.video.currentTime.toFixed(2));
        let kfList;
        if (prop === 'text-pos' || prop === 'text-size') {
            if (!this.state.activeTextId) return;
            const item = this.state.textOverlays.find(o => o.id === this.state.activeTextId);
            if (!item.keyframes) item.keyframes = {};
            if (!item.keyframes[prop]) item.keyframes[prop] = [];
            kfList = item.keyframes[prop];
            const val = prop === 'text-pos' ? {x: item.x, y: item.y} : item.size;
            this.upsertKeyframe(kfList, time, val);
        } else {
            if (!this.state.adjustments.keyframes[prop]) this.state.adjustments.keyframes[prop] = [];
            kfList = this.state.adjustments.keyframes[prop];
            this.upsertKeyframe(kfList, time, this.state.adjustments[prop]);
        }
        this.updateKeyframeMarkers();
    }

    upsertKeyframe(list, time, value) {
        const idx = list.findIndex(k => Math.abs(k.t - time) < 0.1);
        if (idx > -1) list.splice(idx, 1);
        else { list.push({ t: time, v: value }); list.sort((a, b) => a.t - b.t); }
    }

    recordKeyframe(prop, value) {
        const time = this.video.currentTime;
        let list;
        if (prop === 'text-pos' || prop === 'text-size') {
             const item = this.state.textOverlays.find(o => o.id === this.state.activeTextId);
             if (!item || !item.keyframes || !item.keyframes[prop]) return;
             list = item.keyframes[prop];
        } else {
             if (!this.state.adjustments.keyframes[prop]) return;
             list = this.state.adjustments.keyframes[prop];
        }
        const kf = list.find(k => Math.abs(k.t - time) < 0.2);
        if (kf) kf.v = value;
    }

    updateKeyframeMarkers() {
        this.keyframeTrack.innerHTML = '';
        let allKF = [];
        Object.values(this.state.adjustments.keyframes).forEach(list => allKF.push(...list));
        if (this.state.activeTextId) {
            const item = this.state.textOverlays.find(o => o.id === this.state.activeTextId);
            if (item && item.keyframes) Object.values(item.keyframes).forEach(list => allKF.push(...list));
        }
        allKF.forEach(kf => {
            const pct = (kf.t / this.video.duration) * 100;
            const dot = document.createElement('div');
            dot.className = 'kf-marker'; dot.style.left = `${pct}%`;
            this.keyframeTrack.appendChild(dot);
        });
    }

    applyDynamicKeyframes() {
        const time = this.video.currentTime;
        Object.keys(this.state.adjustments.keyframes).forEach(prop => {
            const list = this.state.adjustments.keyframes[prop];
            const val = this.interpolate(list, time);
            if (val !== null) {
                this.state.adjustments[prop] = val;
                const slider = document.querySelector(`.adj-slider[data-filter="${prop}"]`);
                if (slider) slider.value = val;
            }
            const btn = document.querySelector(`.kf-btn[data-prop="${prop}"]`);
            if (btn) btn.classList.toggle('active', list.some(k => Math.abs(k.t - time) < 0.1));
        });
        this.applyFilters();
        this.state.textOverlays.forEach(item => {
            if (item.keyframes) {
                const pos = this.interpolate(item.keyframes['text-pos'], time);
                if (pos) { item.x = pos.x; item.y = pos.y; }
                const size = this.interpolate(item.keyframes['text-size'], time);
                if (size !== null) item.size = size;
                if (item.id === this.state.activeTextId) {
                    ['text-pos', 'text-size'].forEach(prop => {
                        const btn = document.querySelector(`.kf-btn[data-prop="${prop}"]`);
                        if (btn) btn.classList.toggle('active', item.keyframes[prop] && item.keyframes[prop].some(k => Math.abs(k.t - time) < 0.1));
                    });
                }
            }
        });
        this.renderTextOverlays();
    }

    interpolate(list, t) {
        if (!list || list.length === 0) return null;
        if (t <= list[0].t) return list[0].v;
        if (t >= list[list.length - 1].t) return list[list.length - 1].v;
        for (let i = 0; i < list.length - 1; i++) {
            const k1 = list[i], k2 = list[i+1];
            if (t >= k1.t && t <= k2.t) {
                const factor = (t - k1.t) / (k2.t - k1.t);
                if (typeof k1.v === 'object') return { x: k1.v.x + (k2.v.x - k1.v.x) * factor, y: k1.v.y + (k2.v.y - k1.v.y) * factor };
                return k1.v + (k2.v - k1.v) * factor;
            }
        }
        return null;
    }

    setRatio(ratio) {
        this.state.ratio = ratio;
        this.ratioBtns.forEach(btn => { btn.classList.toggle('active', btn.dataset.ratio === ratio); });
        const container = document.getElementById('manualVideoContainer');
        if (ratio === 'original') {
            const vw = this.video.videoWidth, vh = this.video.videoHeight;
            container.style.aspectRatio = vw && vh ? `${vw} / ${vh}` : '';
            container.classList.remove('ratio-forced');
        } else { container.style.aspectRatio = ratio; container.classList.add('ratio-forced'); }
    }

    applyFilters() {
        const adj = this.state.adjustments;
        this.video.style.filter = `brightness(${adj.brightness}%) contrast(${adj.contrast}%) saturate(${adj.saturate}%) sepia(${adj.sepia}%) grayscale(${adj.grayscale}%)`;
    }

    startDragging(e, type, extra = null) {
        e.preventDefault(); e.stopPropagation();
        this.dragging = type;
        if (extra) this.dragStartData = { mouseX: e.clientX, mouseY: e.clientY, ...extra };
    }

    handleDragging(e) {
        if (!this.dragging || !this.isInitialized) return;
        if (this.dragging === 'left' || this.dragging === 'right') {
            const rect = this.trimTrack.getBoundingClientRect();
            let posX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            const time = posX * this.video.duration;
            if (this.dragging === 'left') { 
                if (time < this.state.trimEndIdx - 0.5) { this.state.trimStart = time; this.video.currentTime = time; this.seek.value = time; }
            } else { 
                if (time > this.state.trimStart + 0.5) { this.state.trimEndIdx = time; this.video.currentTime = time; this.seek.value = time; }
            }
            this.updateTrimVisuals();
        } 
        else if (this.dragging.type === 'move') {
            const rect = this.textOverlayContainer.getBoundingClientRect();
            let x = ((e.clientX - rect.left) / rect.width) * 100, y = ((e.clientY - rect.top) / rect.height) * 100;
            const item = this.state.textOverlays.find(o => o.id === this.dragging.id);
            if (item) { item.x = Math.max(0, Math.min(100, x)); item.y = Math.max(0, Math.min(100, y)); this.recordKeyframe('text-pos', {x: item.x, y: item.y}); this.renderTextOverlays(); }
        }
        else if (this.dragging.type === 'resize') {
            const item = this.state.textOverlays.find(o => o.id === this.dragging.id);
            if (item && this.dragStartData) {
                const deltaX = e.clientX - this.dragStartData.mouseX;
                item.size = Math.max(10, Math.min(200, this.dragStartData.initialSize + (deltaX * 0.5)));
                this.recordKeyframe('text-size', item.size); this.renderTextOverlays();
            }
        }
    }

    stopDragging() { this.dragging = null; this.dragStartData = null; }

    updateTrimVisuals() {
        const leftPct = (this.state.trimStart / this.video.duration) * 100;
        const rightPct = (this.state.trimEndIdx / this.video.duration) * 100;
        this.leftHandle.style.left = `${leftPct}%`; this.rightHandle.style.left = `${rightPct}%`;
        this.trimRegion.style.left = `${leftPct}%`; this.trimRegion.style.width = `${rightPct - leftPct}%`;
        this.valTrimStart.innerText = this.state.trimStart.toFixed(1) + 's'; this.valTrimEnd.innerText = this.state.trimEndIdx.toFixed(1) + 's';
    }

    togglePlay() {
        if (this.video.paused) { this.video.play(); this.playPauseBtn.innerText = '⏸️ Pause'; }
        else { this.video.pause(); this.playPauseBtn.innerText = '▶️ Play'; }
    }

    formatTime(seconds) {
        const m = Math.floor(seconds / 60), s = Math.floor(seconds % 60);
        return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
    }

    updateTimelineProgress() {
        const bar = document.getElementById('timelineProgress');
        if (bar) bar.style.width = `${(this.video.currentTime / this.video.duration) * 100}%`;
    }

    checkTrimBounds() {
        if (this.video.currentTime >= this.state.trimEndIdx && !this.video.paused) this.video.currentTime = this.state.trimStart;
    }

    addTextOverlay() {
        const content = this.textContentInput.value.trim();
        if (!content) return;
        const overlay = { 
            id: Date.now(), content: content, x: 50, y: 50, size: 32, font: "'Inter', sans-serif", color: "#ffffff", showBg: true, keyframes: {},
            animation: { in: 'none', out: 'none', loop: 'none', dur: 0.5 }
        };
        this.state.textOverlays.push(overlay);
        this.renderTextOverlays(); this.renderTextList();
        this.textContentInput.value = ''; this.selectText(overlay.id);
    }

    selectText(id) {
        this.state.activeTextId = id; this.renderTextOverlays();
        const tabs = document.getElementById('textTabs');
        if (id) {
            const item = this.state.textOverlays.find(o => o.id === id);
            tabs.style.display = 'flex';
            this.stylingControls.style.display = 'block';
            this.textFont.value = item.font; this.textColor.value = item.color; this.textBgToggle.checked = item.showBg;
            // Sync Animation values
            if (item.animation) {
               this.animIn.value = item.animation.in; this.animOut.value = item.animation.out;
               this.animLoop.value = item.animation.loop; this.animDur.value = item.animation.dur;
            }
        } else { tabs.style.display = 'none'; this.stylingControls.style.display = 'none'; this.animationControls.style.display = 'none'; }
        this.updateKeyframeMarkers();
    }

    updateActiveTextStyles() {
        if (!this.state.activeTextId) return;
        const item = this.state.textOverlays.find(o => o.id === this.state.activeTextId);
        if (item) { item.font = this.textFont.value; item.color = this.textColor.value; item.showBg = this.textBgToggle.checked; this.renderTextOverlays(); }
    }

    updateActiveTextAnimations() {
        if (!this.state.activeTextId) return;
        const item = this.state.textOverlays.find(o => o.id === this.state.activeTextId);
        if (item) {
            item.animation = { in: this.animIn.value, out: this.animOut.value, loop: this.animLoop.value, dur: parseFloat(this.animDur.value) };
            this.renderTextOverlays();
        }
    }

    renderTextOverlays() {
        this.textOverlayContainer.innerHTML = '';
        this.state.textOverlays.forEach(item => {
            const div = document.createElement('div');
            div.className = `text-overlay ${this.state.activeTextId === item.id ? 'selected' : ''}`;
            if (item.animation && item.animation.loop !== 'none') div.classList.add(`anim-${item.animation.loop}`);
            
            // Simple Preview for In-animations (Triggered when playhead is at start)
            if (item.animation && item.animation.in !== 'none' && Math.abs(this.video.currentTime - this.state.trimStart) < 0.3) {
                div.style.transition = `all ${item.animation.dur}s`;
                if (item.animation.in === 'fade') div.style.opacity = '1';
                // Add more complex preview logic as needed
            }

            div.style.left = `${item.x}%`; div.style.top = `${item.y}%`;
            div.style.fontSize = `${item.size}px`; div.style.fontFamily = item.font; div.style.color = item.color;
            div.style.background = item.showBg ? 'rgba(0,0,0,0.4)' : 'transparent';
            div.style.backdropFilter = item.showBg ? 'blur(4px)' : 'none';
            div.innerText = item.content;
            div.onmousedown = (e) => this.startDragging(e, {id: item.id, type: 'move'});
            div.onclick = (e) => { e.stopPropagation(); this.selectText(item.id); };
            ['tl', 'tr', 'bl', 'br'].forEach(pos => {
                const h = document.createElement('div'); h.className = `resize-handle handle-${pos}`;
                h.onmousedown = (e) => this.startDragging(e, {id: item.id, type: 'resize', handle: pos}, {initialSize: item.size});
                div.appendChild(h);
            });
            this.textOverlayContainer.appendChild(div);
        });
    }

    renderTextList() {
        this.textListContainer.innerHTML = '';
        this.state.textOverlays.forEach(item => {
            const div = document.createElement('div'); div.className = 'text-item';
            div.innerHTML = `<span>"${item.content}"</span> <button onclick="window.manualEditor.removeTextOverlay(${item.id})">✕</button>`;
            div.onclick = () => this.selectText(item.id);
            this.textListContainer.appendChild(div);
        });
    }

    removeTextOverlay(id) {
        this.state.textOverlays = this.state.textOverlays.filter(o => o.id !== id);
        if (this.state.activeTextId === id) this.selectText(null);
        this.renderTextOverlays(); this.renderTextList();
    }

    async handleExport() {
        this.exportBtn.disabled = true; this.exportBtn.innerText = 'Applying cinematic edits...';
        this.setStatus('🎬 Rendering cinematic sequence...', 1);
        const formData = new FormData();
        formData.append('video_url', this.state.videoUrl);
        formData.append('edits', JSON.stringify(this.state));
        formData.append('user_email', localStorage.getItem("promptx_user_email"));
        if (this.state.sourceFile) formData.append('video_file', this.state.sourceFile);
        try {
            const response = await fetch('/api/manual-edit', { method: 'POST', body: formData });
            const data = await response.json();
            if (data.error) { alert(`Error: ${data.error}`); this.setStatus('❌ Export failed', 1); }
            else {
                const db = document.getElementById('downloadManualBtn');
                if (db) { db.href = data.video_url; db.style.display = 'block'; }
                this.setStatus('✅ Cinematic render complete!', 0.6);
                this.state.videoUrl = data.video_url; this.video.src = data.video_url; this.video.load();
                this.exportBtn.innerText = '✅ Done!'; setTimeout(() => { this.exportBtn.innerText = 'Apply Edits'; }, 3000);
            }
        } catch (err) { alert(`Export failed: ${err.message}`); this.setStatus('❌ Connection error', 1); }
        finally { this.exportBtn.disabled = false; }
    }
}

window.manualEditor = new ManualEditor();
function initManualEditor(videoUrl) { window.manualEditor.init(videoUrl); }
