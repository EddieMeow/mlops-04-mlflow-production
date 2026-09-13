import mlflow
from mlflow.tracking import MlflowClient

client = MlflowClient()
exp = client.get_experiment_by_name("iris-demo")
best = client.search_runs(
    [exp.experiment_id], order_by=["metrics.accuracy DESC"], max_results=1
)[0]
print("最佳运行:", best.info.run_name, "accuracy=%.4f" % best.data.metrics["accuracy"], flush=True)

# MLflow 3.x：模型是独立实体，用 models:/<model_id> 注册
models = client.search_logged_models(experiment_ids=[exp.experiment_id])
m = [x for x in models if x.source_run_id == best.info.run_id][0]
print("model_id:", m.model_id, flush=True)

result = mlflow.register_model(f"models:/{m.model_id}", "iris-classifier")
print("已注册版本:", result.version, flush=True)
client.set_registered_model_alias("iris-classifier", "champion", result.version)
print("✅ iris-classifier v%s 别名 champion" % result.version, flush=True)
