import os
import mlflow
from mlflow.tracking import MlflowClient

client = MlflowClient()
exp = client.get_experiment_by_name("iris-demo")

# MLflow 3.x：模型是独立实体，不在 runs/<id>/artifacts/ 下
models = client.search_logged_models(experiment_ids=[exp.experiment_id])
m = models[0]
print("model_id :", m.model_id)
print("来源 run :", m.source_run_id)

local = mlflow.artifacts.download_artifacts(f"models:/{m.model_id}")
print("下载到   :", local)
print("文件     :", sorted(os.listdir(local)))
