"""
README용 figure 생성 — reports/*.json(검색·답변 평가 결과)을 읽어 PNG로.
한글 라벨(나눔폰트). 산출: benchmark/figures/F1~F6.png
사용: python -m benchmark.make_figures
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).parent
REP = HERE / "reports"
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)

# ---- 한글 폰트 ----
for _fp in ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/nanum/NanumSquare_acR.ttf",
            "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"):
    if Path(_fp).exists():
        font_manager.fontManager.addfont(_fp)
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=_fp).get_name()
        break
plt.rcParams["axes.unicode_minus"] = False

C_BEST, C_BASE, C_AUG = "#2ca02c", "#4c78a8", "#d62728"


def rpt(name):
    return json.load(open(REP / name, encoding="utf-8"))


def lr_mode(mode):
    return rpt("lightrag_eval.json")["modes"][mode]["overall"]


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("saved", FIG / name)


# ===== F1. 검색 기법 리더보드 (recall@5) =====
def f1_leaderboard():
    rows = [
        ("조청킹+하이브리드+리랭커", rpt("article_hybrid_kure-v1_rerank.json")["overall"]["recall@5"], C_BEST),
        ("조청킹+BM25+리랭커", rpt("article_bm25_rerank.json")["overall"]["recall@5"], C_BASE),
        ("조청킹+BM25", rpt("article_bm25.json")["overall"]["recall@5"], C_BASE),
        ("조청킹+하이브리드(RRF)", rpt("article_hybrid_kure-v1.json")["overall"]["recall@5"], C_BASE),
        ("LightRAG(naive)", lr_mode("naive")["recall@5"], C_AUG),
        ("HyDE+하이브리드+리랭커", rpt("article_hybrid_kure-v1_hyde_rerank_byp-md.json")["overall"]["recall@5"], C_AUG),
        ("조청킹+벡터(KURE)+리랭커", rpt("article_vector_kure-v1_rerank.json")["overall"]["recall@5"], C_BASE),
        ("조청킹+벡터(KURE)", rpt("article_vector_kure-v1.json")["overall"]["recall@5"], C_BASE),
        ("HyPE", rpt("article_bm25_kure-v1_hype.json")["overall"]["recall@5"], C_AUG),
        ("LightRAG(mix)", lr_mode("mix")["recall@5"], C_AUG),
        ("HyDE(벡터)", rpt("article_vector_kure-v1_hyde_byp-md.json")["overall"]["recall@5"], C_AUG),
    ]
    rows.sort(key=lambda x: x[1])
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    cols = [r[2] for r in rows]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    bars = ax.barh(labels, vals, color=cols)
    for b, v in zip(bars, vals):
        ax.text(v + 0.005, b.get_y() + b.get_height() / 2, f"{v:.3f}", va="center", fontsize=9)
    ax.set_xlim(0.6, 0.9)
    ax.set_xlabel("recall@5 (240문)")
    ax.set_title("F1. 검색 기법 리더보드 — 하이브리드+리랭커가 최적")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=C_BEST, label="최적"), Patch(color=C_BASE, label="기본 기법"),
                       Patch(color=C_AUG, label="증강 기법(부정 결과)")], loc="lower right", fontsize=8)
    save(fig, "F1_retrieval_leaderboard.png")


# ===== F2. 검색기 × 질문유형 (recall@5) =====
def f2_by_type():
    types = ["factoid", "crossref", "byeolpyo", "multihop"]
    series = [
        ("BM25", rpt("article_bm25.json"), C_BASE),
        ("벡터(KURE)", rpt("article_vector_kure-v1.json"), "#f58518"),
        ("하이브리드+리랭커", rpt("article_hybrid_kure-v1_rerank.json"), C_BEST),
    ]
    import numpy as np
    x = np.arange(len(types))
    w = 0.26
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for i, (name, d, col) in enumerate(series):
        vals = [d["by_type"][t]["recall@5"] for t in types]
        bars = ax.bar(x + (i - 1) * w, vals, w, label=name, color=col)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.2f}", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(["factoid\n(정의·요건)", "crossref\n(교차참조)", "byeolpyo\n(별표)", "multihop\n(법↔시행령)"])
    ax.set_ylabel("recall@5")
    ax.set_ylim(0, 1.08)
    ax.set_title("F2. 검색기 × 질문유형 — 유형마다 강한 검색이 다름")
    ax.legend(fontsize=9)
    save(fig, "F2_retriever_by_type.png")


# ===== F3. 컴포넌트 ablation — recall@k 곡선 =====
def f3_recall_at_k():
    ks = [1, 3, 5, 10]
    series = [
        ("BM25", rpt("article_bm25.json"), "o", C_BASE),
        ("벡터(KURE)", rpt("article_vector_kure-v1.json"), "s", "#f58518"),
        ("하이브리드(RRF)", rpt("article_hybrid_kure-v1.json"), "^", "#9467bd"),
        ("하이브리드+리랭커", rpt("article_hybrid_kure-v1_rerank.json"), "D", C_BEST),
    ]
    fig, ax = plt.subplots(figsize=(7, 4.6))
    for name, d, mk, col in series:
        vals = [d["overall"][f"recall@{k}"] for k in ks]
        ax.plot(ks, vals, marker=mk, label=name, color=col, linewidth=2)
    ax.set_xticks(ks)
    ax.set_xlabel("k")
    ax.set_ylabel("recall@k")
    ax.set_title("F3. 컴포넌트 누적 효과 — 리랭커가 단일 최대 레버")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9)
    save(fig, "F3_recall_at_k.png")


# ===== F4. 증강 기법 부정 결과 =====
def f4_augmentation():
    base_best = rpt("article_hybrid_kure-v1_rerank.json")["overall"]["recall@5"]
    base_vec = rpt("article_vector_kure-v1.json")["overall"]["recall@5"]
    rows = [
        ("하이브리드+리랭커\n(최적 baseline)", base_best, C_BEST),
        ("벡터(KURE)\n(baseline)", base_vec, C_BASE),
        ("HyPE\n(색인측 증강)", rpt("article_bm25_kure-v1_hype.json")["overall"]["recall@5"], C_AUG),
        ("HyDE\n(질의측 증강)", rpt("article_vector_kure-v1_hyde_byp-md.json")["overall"]["recall@5"], C_AUG),
        ("LightRAG\n(그래프, 최고모드)", lr_mode("naive")["recall@5"], C_AUG),
    ]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    bars = ax.bar([r[0] for r in rows], [r[1] for r in rows], color=[r[2] for r in rows])
    for b, r in zip(bars, rows):
        ax.text(b.get_x() + b.get_width() / 2, r[1] + 0.008, f"{r[1]:.3f}", ha="center", fontsize=9)
    ax.axhline(base_best, color=C_BEST, ls="--", lw=1, alpha=0.7)
    ax.axhline(base_vec, color=C_BASE, ls="--", lw=1, alpha=0.7)
    ax.set_ylim(0.6, 0.9)
    ax.set_ylabel("recall@5")
    ax.set_title("F4. 증강 기법 모두 baseline 미달 — 정교한 기법 ≠ 더 나음")
    save(fig, "F4_augmentation_negative.png")


# ===== F5. 격식체 vs 구어체 =====
def f5_register():
    series = [
        ("BM25", rpt("article_bm25.json")),
        ("벡터(KURE)", rpt("article_vector_kure-v1.json")),
        ("하이브리드+리랭커", rpt("article_hybrid_kure-v1_rerank.json")),
    ]
    import numpy as np
    x = np.arange(len(series))
    w = 0.36
    fig, ax = plt.subplots(figsize=(7, 4.4))
    formal = [d["by_register"]["formal"]["recall@5"] for _, d in series]
    collo = [d["by_register"]["colloquial"]["recall@5"] for _, d in series]
    b1 = ax.bar(x - w / 2, formal, w, label="격식체(formal)", color="#4c78a8")
    b2 = ax.bar(x + w / 2, collo, w, label="구어체(colloquial)", color="#54a24b")
    for bs in (b1, b2):
        for b in bs:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.01, f"{b.get_height():.2f}", ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([s[0] for s in series])
    ax.set_ylabel("recall@5 (factoid 쌍)")
    ax.set_ylim(0, 1.1)
    ax.set_title("F5. 구어체 ≥ 격식체 — 질의측 어휘격차가 작다(반직관)")
    ax.legend(fontsize=9)
    save(fig, "F5_register.png")


# ===== F6. 답변모델 비교 (heatmap) =====
def f6_answer_models():
    import numpy as np
    metrics = ["correctness", "faithfulness", "relevancy", "completeness", "context_utilization", "cite_f1"]
    mlabels = ["정확성", "충실성", "적합성", "완결성", "맥락활용", "인용F1"]
    files = {
        "gemma-4-31B": "answer_google_gemma-4-31B-it_good.json",
        "A.X-4.0 (67B)": "answer_skt_A.X-4.0_good.json",
        "EXAONE-4.0-32B": "answer_LGAI-EXAONE_EXAONE-4.0-32B_good.json",
        "Qwen3.6-27B": "answer_Qwen_Qwen3.6-27B_good.json",
        "Solar-Open-100B": "answer_upstage_Solar-Open-100B_good.json",
    }
    data, names = [], []
    for name, f in files.items():
        o = rpt(f)["overall"]
        data.append([o[m] for m in metrics])
        names.append(name)
    data = np.array(data)
    order = np.argsort(-data.mean(axis=1))  # 평균 높은 순
    data, names = data[order], [names[i] for i in order]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    im = ax.imshow(data, cmap="YlGn", vmin=0.4, vmax=0.85, aspect="auto")
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(mlabels)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    for i in range(len(names)):
        for j in range(len(metrics)):
            ax.text(j, i, f"{data[i, j]:.2f}", ha="center", va="center", fontsize=9)
    ax.set_title("F6. 답변모델 비교 (judge 0~1) — gemma-4-31B 최고, 크기≠품질")
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    save(fig, "F6_answer_models.png")


if __name__ == "__main__":
    f1_leaderboard()
    f2_by_type()
    f3_recall_at_k()
    f4_augmentation()
    f5_register()
    f6_answer_models()
    print("\n모든 figure 생성 완료 →", FIG)
