"""
README용 figure 생성 — reports/*.json(검색·답변 평가 결과)을 읽어 PNG로.
한글 라벨(나눔폰트), dpi 300, 제목 없음(캡션은 README에서). 산출: benchmark/figures/fig_00~07.png
사용: python -m benchmark.make_figures
"""
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch

HERE = Path(__file__).parent
REP = HERE / "reports"
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)
DPI = 300

# ---- 한글 폰트 ----
for _fp in ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/nanum/NanumSquare_acR.ttf",
            "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"):
    if Path(_fp).exists():
        font_manager.fontManager.addfont(_fp)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=_fp).get_name()
        break

# ---- 공통 스타일(세련된 톤) ----
plt.rcParams.update({
    "axes.unicode_minus": False,
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": "#9aa0a6",
    "axes.linewidth": 0.8,
    "axes.titlesize": 12,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

# 절제된 팔레트(teal/slate/brick + 보조 gold·mauve)
BEST = "#2a9d8f"   # teal — 최적
BASE = "#577590"   # slate — 기본 기법
AUG = "#b5524f"    # muted brick — 증강(부정)
GOLD = "#e9c46a"   # 보조
MAUVE = "#a26769"  # 보조
INK = "#2b2b2b"
SIZE_STD = (7.2, 4.6)   # F2·F3·F4 공통 크기


def rpt(name):
    return json.load(open(REP / name, encoding="utf-8"))


def lr_mode(mode):
    return rpt("lightrag_eval.json")["modes"][mode]["overall"]


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print("saved", FIG / name)


# ===== 그림0. 방법론 파이프라인 (손그림 2행) =====
def f0_pipeline():
    import matplotlib.patches as mpatches
    LIGHT, STAGE = "#eef2f4", "#bfe3dd"   # 일반 박스 / 단계 박스(연한 teal)
    BW, BH = 2.7, 1.55
    with plt.rc_context({"path.sketch": (1.6, 110, 14), "font.size": 10}):  # 손그림 wiggle
        fig, ax = plt.subplots(figsize=(9.6, 5.4))
        ax.set_xlim(0, 12.4)
        ax.set_ylim(0, 7)
        ax.axis("off")

        def box(cx, cy, text, fc, fs=9.5):
            ax.add_patch(mpatches.FancyBboxPatch(
                (cx - BW / 2, cy - BH / 2), BW, BH,
                boxstyle="round,pad=0.05,rounding_size=0.22",
                linewidth=2.0, facecolor=fc, edgecolor=INK))
            ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color=INK, zorder=5)

        def arrow(p1, p2):
            ax.annotate("", xy=p2, xytext=p1,
                        arrowprops=dict(arrowstyle="-|>", lw=2.0, color=INK, shrinkA=3, shrinkB=3))

        y1, y2 = 5.2, 1.7
        cx = [1.7, 4.85, 8.0, 10.7]   # 행1 4칸
        box(cx[0], y1, "법령 XML\n· 별표 PDF", LIGHT)
        box(cx[1], y1, "코퍼스 32법령\n(약 3,251 청크)", LIGHT)
        box(cx[2], y1, "골드셋 240문\nLLM생성 + 일관성필터", LIGHT)
        box(cx[3], y1, "1단계 · 검색 평가\n(청킹·임베딩·검색기\n·리랭커)", STAGE, fs=9)
        cx2 = [10.7, 6.2, 1.7]        # 행2 (우→좌)
        box(cx2[0], y2, "검색 지표\nrecall@k·MRR·nDCG\n(gold = uid)", LIGHT)
        box(cx2[1], y2, "2단계 · 답변 평가\n(답변모델 + judge\n+ 인용검증)", STAGE, fs=9)
        box(cx2[2], y2, "답변 지표\n정확성·충실성\n완결성·인용", LIGHT)
        for a, b in [(0, 1), (1, 2), (2, 3)]:
            arrow((cx[a] + BW / 2, y1), (cx[b] - BW / 2, y1))
        arrow((cx[3], y1 - BH / 2), (cx2[0], y2 + BH / 2))           # 단계 전환(아래로)
        arrow((cx2[0] - BW / 2, y2), (cx2[1] + BW / 2, y2))
        arrow((cx2[1] - BW / 2, y2), (cx2[2] + BW / 2, y2))
        ax.text(cx[3] + 0.15, (y1 + y2) / 2, "최적 구성\n고정", ha="left", va="center",
                fontsize=8.5, color=AUG, style="italic")
        save(fig, "fig_00_pipeline.png")


# ===== 청킹 비교 (E1, recall@5) =====
def f_chunking():
    chunkers = [("조(article)", "article"), ("항(hang)", "hang"),
                ("고정토큰(fixed)", "fixed"), ("계층(parent)", "parent")]
    bm25 = [rpt(f"{c}_bm25.json")["overall"]["recall@5"] for _, c in chunkers]
    vec = [rpt(f"{c}_vector_kure-v1.json")["overall"]["recall@5"] for _, c in chunkers]
    x = np.arange(len(chunkers))
    w = 0.38
    fig, ax = plt.subplots(figsize=SIZE_STD)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#ececec", lw=0.7)
    b1 = ax.bar(x - w / 2, bm25, w, label="BM25", color=BASE, edgecolor="white", linewidth=0.6)
    b2 = ax.bar(x + w / 2, vec, w, label="벡터(KURE)", color=GOLD, edgecolor="white", linewidth=0.6)
    for bs in (b1, b2):
        for b in bs:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.012, f"{b.get_height():.2f}",
                    ha="center", fontsize=8, color=INK)
    ax.set_xticks(x, labels=[c[0] for c in chunkers])
    ax.set_ylabel("recall@5")
    ax.set_ylim(0, 1.0)
    ax.legend(fontsize=9, frameon=True, edgecolor="#dddddd")
    save(fig, "fig_02_chunking.png")


# ===== F2. 검색기 × 질문유형 (recall@5) =====
def f2_by_type():
    types = ["factoid", "crossref", "byeolpyo", "multihop"]
    series = [("BM25", rpt("article_bm25.json"), BASE),
              ("벡터(KURE)", rpt("article_vector_kure-v1.json"), GOLD),
              ("하이브리드+리랭커", rpt("article_hybrid_kure-v1_rerank.json"), BEST)]
    x = np.arange(len(types))
    w = 0.26
    fig, ax = plt.subplots(figsize=SIZE_STD)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#ececec", lw=0.7)
    for i, (name, d, col) in enumerate(series):
        vals = [d["by_type"][t]["recall@5"] for t in types]
        bars = ax.bar(x + (i - 1) * w, vals, w, label=name, color=col, edgecolor="white", linewidth=0.6)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.012, f"{v:.2f}", ha="center", fontsize=8, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels(["factoid\n(정의·요건)", "crossref\n(교차참조)", "byeolpyo\n(별표)", "multihop\n(법↔시행령)"])
    ax.set_ylabel("recall@5")
    ax.set_ylim(0, 1.1)
    ax.legend(fontsize=9, frameon=True, edgecolor="#dddddd")
    save(fig, "fig_03_by_type.png")


# ===== F3. 컴포넌트 ablation — recall@k 곡선 =====
def f3_recall_at_k():
    ks = [1, 3, 5, 10]
    series = [("BM25", rpt("article_bm25.json"), "o", BASE),
              ("벡터(KURE)", rpt("article_vector_kure-v1.json"), "s", GOLD),
              ("하이브리드(RRF)", rpt("article_hybrid_kure-v1.json"), "^", MAUVE),
              ("하이브리드+리랭커", rpt("article_hybrid_kure-v1_rerank.json"), "D", BEST)]
    fig, ax = plt.subplots(figsize=SIZE_STD)
    ax.set_axisbelow(True)
    ax.grid(color="#ececec", lw=0.7)
    for name, d, mk, col in series:
        vals = [d["overall"][f"recall@{k}"] for k in ks]
        ax.plot(ks, vals, marker=mk, label=name, color=col, linewidth=2.2, markersize=6,
                markeredgecolor="white", markeredgewidth=0.6)
    ax.set_xticks(ks)
    ax.set_xlabel("k")
    ax.set_ylabel("recall@k")
    ax.legend(fontsize=9, frameon=True, edgecolor="#dddddd")
    save(fig, "fig_04_recall_at_k.png")


# ===== F4. 증강 기법 부정 결과 (크기: F2/F3과 동일) =====
def f4_augmentation():
    base_best = rpt("article_hybrid_kure-v1_rerank.json")["overall"]["recall@5"]
    base_vec = rpt("article_vector_kure-v1.json")["overall"]["recall@5"]
    rows = [("하이브리드+리랭커\n(최적 baseline)", base_best, BEST),
            ("벡터(KURE)\n(baseline)", base_vec, BASE),
            ("HyPE\n(색인측 증강)", rpt("article_bm25_kure-v1_hype.json")["overall"]["recall@5"], AUG),
            ("HyDE\n(질의측 증강)", rpt("article_vector_kure-v1_hyde_byp-md.json")["overall"]["recall@5"], AUG),
            ("LightRAG\n(그래프, 최고모드)", lr_mode("naive")["recall@5"], AUG)]
    fig, ax = plt.subplots(figsize=SIZE_STD)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#ececec", lw=0.7)
    bars = ax.bar([r[0] for r in rows], [r[1] for r in rows], color=[r[2] for r in rows],
                  edgecolor="white", linewidth=0.6, width=0.62)
    for b, r in zip(bars, rows):
        ax.text(b.get_x() + b.get_width() / 2, r[1] + 0.007, f"{r[1]:.3f}", ha="center", fontsize=9, color=INK)
    ax.axhline(base_best, color=BEST, ls="--", lw=1, alpha=0.6)
    ax.axhline(base_vec, color=BASE, ls="--", lw=1, alpha=0.6)
    ax.set_ylim(0.6, 0.9)
    ax.set_ylabel("recall@5")
    save(fig, "fig_05_augmentation.png")


# ===== F5. 격식체 vs 구어체 =====
def f5_register():
    series = [("BM25", rpt("article_bm25.json")),
              ("벡터(KURE)", rpt("article_vector_kure-v1.json")),
              ("하이브리드+리랭커", rpt("article_hybrid_kure-v1_rerank.json"))]
    x = np.arange(len(series))
    w = 0.36
    fig, ax = plt.subplots(figsize=(7, 4.4))
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#ececec", lw=0.7)
    formal = [d["by_register"]["formal"]["recall@5"] for _, d in series]
    collo = [d["by_register"]["colloquial"]["recall@5"] for _, d in series]
    b1 = ax.bar(x - w / 2, formal, w, label="격식체(formal)", color=BASE, edgecolor="white", linewidth=0.6)
    b2 = ax.bar(x + w / 2, collo, w, label="구어체(colloquial)", color=BEST, edgecolor="white", linewidth=0.6)
    for bs in (b1, b2):
        for b in bs:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.012, f"{b.get_height():.2f}",
                    ha="center", fontsize=8, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([s[0] for s in series])
    ax.set_ylabel("recall@5 (factoid 쌍)")
    ax.set_ylim(0, 1.12)
    ax.legend(fontsize=9, frameon=True, edgecolor="#dddddd")
    save(fig, "fig_06_register.png")


# ===== F8. 어휘중첩 편향 검증 — 원본 vs 저어휘중첩 (dumbbell) =====
def f8_lowoverlap():
    # (라벨, 원본리포트, 저중첩리포트)
    rows = [
        ("BM25 (어휘)",            "article_bm25_byp-md",                       "article_bm25_byp-md_lowoverlap"),
        ("벡터 KURE (dense)",      "article_vector_kure-v1",                    "article_vector_kure-v1_byp-md_lowoverlap"),
        ("하이브리드 (RRF)",       "article_hybrid_kure-v1",                    "article_hybrid_kure-v1_byp-md_lowoverlap"),
        ("하이브리드+리랭커",      "article_hybrid_kure-v1_rerank",             "article_hybrid_kure-v1_rerank_byp-md_lowoverlap"),
        ("벡터+리랭커",            "article_vector_kure-v1_rerank",             "article_vector_kure-v1_rerank_byp-md_lowoverlap"),
        ("HyPE (색인측)",          "article_bm25_kure-v1_hype",                 "article_bm25_kure-v1_hype_byp-md_lowoverlap"),
        ("HyDE (벡터)",            "article_vector_kure-v1_hyde_byp-md",        "article_vector_kure-v1_hyde_byp-md_lowoverlap"),
        ("HyDE (하이브리드+리랭커)", "article_hybrid_kure-v1_hyde_rerank_byp-md", "article_hybrid_kure-v1_hyde_rerank_byp-md_lowoverlap"),
    ]
    data = [(lab, rpt(f"{o}.json")["overall"]["recall@5"], rpt(f"{l}.json")["overall"]["recall@5"])
            for lab, o, l in rows]
    data.sort(key=lambda r: r[1])  # 원본 기준 오름차순(위가 높음)
    labels = [d[0] for d in data]
    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#ececec", lw=0.7)
    for i, (_, ov, lo) in enumerate(data):
        ax.plot([ov, lo], [i, i], color="#c9ccd1", lw=2.0, zorder=1)   # 중립 연결선(길이=변화 크기)
        ax.scatter(ov, i, color=BASE, s=70, zorder=3, edgecolor="white", linewidth=0.8)
        ax.scatter(lo, i, color=AUG, s=70, zorder=3, edgecolor="white", linewidth=0.8)
        ax.text(min(ov, lo) - 0.012, i, f"{min(ov, lo):.2f}", va="center", ha="right", fontsize=8, color=INK)
        ax.text(max(ov, lo) + 0.012, i, f"{max(ov, lo):.2f}", va="center", ha="left", fontsize=8, color=INK)
    ax.set_yticks(y, labels=labels)
    ax.set_xlim(0.45, 0.92)
    ax.set_xlabel("recall@5 (240문)")
    ax.legend(handles=[Patch(color=BASE, label="Lexical Benchmark"),
                       Patch(color=AUG, label="Semantic Benchmark")],
              loc="lower right", fontsize=8.5, frameon=True, edgecolor="#dddddd")
    save(fig, "fig_07_lowoverlap.png")


if __name__ == "__main__":
    # 그림0(fig_00_pipeline.png)은 외부에서 별도 관리(손그림 도식) — 자동 생성 제외.
    # 필요 시 f0_pipeline()을 직접 호출해 matplotlib 버전으로 재생성 가능.
    # 리더보드(구 fig_01)는 표 1과 중복이라 README에서 제외 — figure 미생성.
    f_chunking()
    f2_by_type()
    f3_recall_at_k()
    f4_augmentation()
    f5_register()
    f8_lowoverlap()
    # 답변모델 히트맵(구 fig_06_answer_models)은 표 8과 중복이라 README에서 제외 — figure 미생성.
    print("\n모든 figure 생성 완료 →", FIG)
