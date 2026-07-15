// 状態をオブジェクトに集約
const viewport = {
    scale: 1,
    pointX: 0,
    pointY: 0
};

let timelineData = [];
let currentIndex = 0;
let isDragging = false, startX = 0, startY = 0;
const container = document.getElementById('svg-container');
const zoomArea = document.getElementById('zoom-area');

async function init() {
    const res = await fetch('timeline.json');
    timelineData = await res.json();
    const inner = document.getElementById('timeline-inner');
    timelineData.forEach((ev, i) => {
        const div = document.createElement('div');
        div.className = 'dot-wrapper';
        div.innerHTML = `<div class="timeline-dot" id="dot-${i}"></div><div class="label-year">${ev.year}</div><div class="label-era">${ev.era}</div>`;
        div.onclick = () => selectEvent(i);
        inner.appendChild(div);
    });
    selectEvent(0);
}

let isFirstLoad = true; // 初回読み込みフラグ

async function selectEvent(i) {
    if (i < 0 || i >= timelineData.length) return;
    currentIndex = i;
    const ev = timelineData[i];

    // UI更新：タイトルをヘッダーに表示
    document.querySelectorAll('.timeline-dot').forEach((d, idx) => d.classList.toggle('active', idx === i));
    document.getElementById('title-box').textContent = ev.title; 
    document.getElementById('explanation-box').textContent = ev.exp;
    document.getElementById('prev-btn').disabled = (i === 0);
    document.getElementById('next-btn').disabled = (i === timelineData.length - 1);

    // タイムラインスクロール
    const scrollArea = document.getElementById('scroll-area');
    const target = document.getElementById(`dot-${i}`).parentElement;
    scrollArea.scrollTo({ left: target.offsetLeft - scrollArea.offsetWidth / 2 + 50, behavior: 'smooth' });

    // SVG読み込み
    try {
        const svgRes = await fetch(ev.file);
        container.innerHTML = await svgRes.text();

        // 初回ロード時のみ強制リセット。最初に後醍醐天皇が見える場所に持っていく。
        if (isFirstLoad) {
            viewport.scale = 1;
            viewport.pointX = 230;
            viewport.pointY = 440;
            isFirstLoad = false; // 一度通ったらフラグを倒す
        }

        updateTransform();
    } catch (e) {
        container.innerHTML = '図の読み込みに失敗しました';
    }
}

function updateTransform() {
    container.style.transform = `translate(${viewport.pointX}px, ${viewport.pointY}px) scale(${viewport.scale})`;
}

zoomArea.addEventListener('mousedown', (e) => {
    isDragging = true;
    startX = e.clientX - viewport.pointX;
    startY = e.clientY - viewport.pointY;
});

window.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    viewport.pointX = e.clientX - startX;
    viewport.pointY = e.clientY - startY;
    updateTransform();
});

window.addEventListener('mouseup', () => isDragging = false);

zoomArea.addEventListener('wheel', (e) => {
    e.preventDefault();
    viewport.scale = Math.min(Math.max(viewport.scale + (e.deltaY > 0 ? -0.1 : 0.1), 0.2), 3);
    updateTransform();
}, { passive: false });

document.getElementById('prev-btn').onclick = () => selectEvent(currentIndex - 1);
document.getElementById('next-btn').onclick = () => selectEvent(currentIndex + 1);

init();
