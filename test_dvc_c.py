import mlflow
from mlflow.tracking import MlflowClient

client = MlflowClient()
exp = client.get_experiment_by_name("wine-dvc")
runs = client.search_runs([exp.experiment_id], order_by=["attributes.start_time ASC"])
oldest = runs[0]
print("run_id  :", oldest.info.run_id, flush=True)
print("data_md5:", oldest.data.params["data_md5"], flush=True)
print("rows    :", oldest.data.params["data_rows"], flush=True)
print("git     :", oldest.data.tags.get("git_commit"), flush=True)
