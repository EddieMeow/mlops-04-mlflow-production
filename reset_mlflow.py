import time
import mlflow
from mlflow.tracking import MlflowClient

c = MlflowClient()

for m in c.search_registered_models():
    c.delete_registered_model(m.name)
    print("删除模型:", m.name)

# 先改名再删除：MLflow 是软删除，不改名的话同名实验建不回来
for e in c.search_experiments():
    if e.name != "Default":
        c.rename_experiment(e.experiment_id, "%s-old-%d" % (e.name, int(time.time())))
        c.delete_experiment(e.experiment_id)
        print("归档实验:", e.name)

print("✅ 已清空")
