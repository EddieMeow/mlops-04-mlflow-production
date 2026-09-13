import hashlib
import subprocess
from pathlib import Path

import mlflow
import pandas as pd
import yaml
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import train_test_split

DATA = Path("data/wine_sample.csv")


def dvc_md5():
    """读取 DVC 为该数据集记录的 md5"""
    pointer = Path(str(DATA) + ".dvc")
    if not pointer.exists():
        return None
    return yaml.safe_load(pointer.read_text())["outs"][0]["md5"]


def file_md5():
    """计算磁盘上文件的实际 md5"""
    return hashlib.md5(DATA.read_bytes()).hexdigest()


def git_rev():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


df = pd.read_csv(DATA)
X = df.drop(columns=["quality"])
y = df["quality"]
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, random_state=42)

tracked, actual = dvc_md5(), file_md5()

mlflow.set_experiment("wine-dvc")
with mlflow.start_run() as run:
    model = RandomForestRegressor(n_estimators=50, random_state=42).fit(X_tr, y_tr)
    rmse = mean_squared_error(y_te, model.predict(X_te)) ** 0.5

    # --- 数据血缘记录 ---
    mlflow.log_param("data_md5", tracked)
    mlflow.log_param("data_rows", len(df))
    mlflow.set_tag("git_commit", git_rev())
    mlflow.set_tag("data_verified", str(tracked == actual))

    mlflow.log_metric("rmse", rmse)
    mlflow.sklearn.log_model(model, name="model")

    print("run_id   :", run.info.run_id, flush=True)
    print("data_md5 :", tracked, flush=True)
    print("rows     : %d   rmse: %.4f" % (len(df), rmse), flush=True)
    if tracked != actual:
        print("⚠️  数据不一致 — 磁盘 %s，DVC 记录 %s" % (actual, tracked), flush=True)
