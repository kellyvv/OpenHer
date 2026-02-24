#!/usr/bin/env python3
"""Extract chart data from eval_results/v3/ for the project page web charts."""
import json, os, glob
from collections import defaultdict
import numpy as np
from sklearn.decomposition import PCA

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "eval_results", "v3")

def load_all():
    """Load all experiment JSONs, grouped by model > method."""
    data = defaultdict(lambda: defaultdict(list))
    for fp in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json"))):
        if fp.endswith("_checkpoint.json"):
            continue
        with open(fp) as f:
            d = json.load(f)
        meta = d.get("meta", {})
        model = meta.get("model", "")
        method = meta.get("method", "")
        if model and method:
            data[model][method].append(d)
    return data

def extract_pca_data(data, target_model="qwen3-max"):
    """Extract emotion vectors for PCA projection (qwen3-max only for clarity)."""
    method_labels = {
        "baseline_prompt": "Baseline-Prompt",
        "baseline_reflexion": "Reflexion",
        "v8_full": "TPE-Full",
    }
    all_vecs = []
    all_methods = []
    all_crystallized = []
    
    model_data = data.get(target_model, {})
    for method in ["baseline_prompt", "baseline_reflexion", "v8_full"]:
        runs = model_data.get(method, [])
        for run in runs:
            for r in run.get("results", []):
                ev = r.get("emotion_vec", {})
                if ev:
                    vec = [ev.get("affiliation", 0.5), ev.get("dominance", 0.5), ev.get("novelty", 0.5)]
                    all_vecs.append(vec)
                    all_methods.append(method_labels.get(method, method))
                    all_crystallized.append(r.get("crystallized", False))
    
    if not all_vecs:
        return []
    
    X = np.array(all_vecs)
    pca = PCA(n_components=2)
    X2 = pca.fit_transform(X)
    
    points = []
    for i in range(len(X2)):
        points.append({
            "x": round(float(X2[i, 0]), 4),
            "y": round(float(X2[i, 1]), 4),
            "method": all_methods[i],
            "crystal": all_crystallized[i],
        })
    
    variance_ratio = [round(float(v), 4) for v in pca.explained_variance_ratio_]
    return {"points": points, "variance_ratio": variance_ratio}

def extract_collapse_data(data):
    """Extract collapse index per model for the bar chart."""
    models_order = ["qwen3-max", "MiniMax-M2.5", "gpt-5-mini"]
    methods = ["baseline_prompt", "v8_full"]
    method_labels = {"baseline_prompt": "Baseline-Prompt", "v8_full": "TPE-Full"}
    
    result = []
    for model in models_order:
        model_data = data.get(model, {})
        model_entry = {"model": model}
        for method in methods:
            runs = model_data.get(method, [])
            vals = []
            for run in runs:
                ci = run.get("metrics", {}).get("rlhf_collapse_index", 0)
                if isinstance(ci, (int, float)):
                    vals.append(ci)
            avg = round(float(np.mean(vals)), 4) if vals else 0
            model_entry[method_labels[method]] = avg
        result.append(model_entry)
    return result


if __name__ == "__main__":
    data = load_all()
    print(f"Loaded models: {list(data.keys())}")
    
    # PCA data
    pca_data = extract_pca_data(data)
    print(f"PCA points: {len(pca_data['points'])}")
    print(f"Variance ratio: {pca_data['variance_ratio']}")
    
    # Collapse data
    collapse_data = extract_collapse_data(data)
    print(f"Collapse data: {json.dumps(collapse_data, indent=2)}")
    
    # Write to project-page/src/data/
    out_dir = os.path.join(os.path.dirname(__file__), "..", "project-page", "src", "data")
    os.makedirs(out_dir, exist_ok=True)
    
    with open(os.path.join(out_dir, "pca_data.json"), "w") as f:
        json.dump(pca_data, f)
    print(f"Wrote pca_data.json ({os.path.getsize(os.path.join(out_dir, 'pca_data.json'))} bytes)")
    
    with open(os.path.join(out_dir, "collapse_data.json"), "w") as f:
        json.dump(collapse_data, f)
    print(f"Wrote collapse_data.json")
