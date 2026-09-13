# MLflow 生产部署（二）测试篇 — 验证状态存活与清理

验证 MLflow 的状态真的存在**集群之外**：删掉 Pod、缩容到 0、甚至删掉整个集群，
实验记录和模型文件都不会丢。

- **前提：** 已完成 [搭建篇](MLFLOW_生产部署_搭建篇.md)，Pod 处于 `1/1 Running`，
  端口转发运行中，http://localhost:5000 可以打开。
- **耗时：** 约 15 分钟。
- **实测：** 本篇用例已在本机部分跑通，状态见下表；凡标 ✅ 的都是真实执行结果。
- **看界面：** 配合 [MLflow UI 使用指南](MLFLOW_UI_使用指南.md) 更容易理解每一步。

### 本系列文档

| 文档 | 内容 |
| --- | --- |
| [搭建篇](MLFLOW_生产部署_搭建篇.md) | 架构、前置条件、建库建表、装 MLflow、故障排查 |
| **本篇（测试篇）** | 测试用例 A/B/C/D、结果对照表、环境清理 |
| [英文原版](MLFLOW_PRODUCTION_PLAN.md) | 本文档的英文版 |

---

> ## ✅ 实测状态（2026-09-13）
>
> | 用例 | 内容 | 状态 |
> | --- | --- | --- |
> | **A** | 记录 3 次运行 | ✅ **已通过** —— 3 条记录入库，**15 个对象**入 S3 |
> | **B1** | 从 PostgreSQL 直接读指标 | ✅ **已通过** |
> | **B2** | 删掉 Pod | ✅ **已通过** —— 新 Pod 就绪后记录仍为 3 条 |
> | **B3** | 缩容到 0 ⭐ | ✅ **已通过** —— `No resources found`，0 个 Pod 时记录仍为 3 条 |
> | B4 | 删掉整个集群 | ⬜ 未执行（会拆掉环境，建议最后做） |
> | **C1/C2** | 产出文件在 S3 且存活 | ✅ **已通过** —— Pod 重建 **2 次**后 15 个对象完好 |
> | C3 | 经客户端下载产出文件 | ⬜ 未执行（执行方式已修正，见 [C3](#c3-通过-mlflow-客户端下载产出文件)） |
> | D | 模型注册表往返 | ⬜ 未执行（`model_versions` 表当前为 0 行） |
>
> ### 🔧 实测修正
>
> | # | 位置 | 问题 |
> | --- | --- | --- |
> | ③ | [C1](#c1-确认产出文件真的在-s3-里) | 原判据「`artifact_location` 以 `s3://` 开头」**不成立** —— 代理模式下存的是 `mlflow-artifacts:/1` |
> | ④ | [C3](#c3-通过-mlflow-客户端下载产出文件) | 原写法 `uv run python - <<'PYEOF'` 会**卡住不执行**，须改为脚本文件 |

---

## 目录

1. [测试前准备](#1-测试前准备)
2. [用例 A — 记录一次真实运行](#2-用例-a--记录一次真实运行)
3. [用例 B — 状态存活在外部数据库 ⭐](#3-用例-b--状态存活在外部数据库-)
4. [用例 C — 产出文件在 S3 的持久性](#4-用例-c--产出文件在-s3-的持久性)
5. [用例 D — 模型注册表往返](#5-用例-d--模型注册表往返)
6. [结果对照表](#6-结果对照表)
7. [环境清理](#7-环境清理)

---

## 1. 测试前准备

端口转发要**保持运行**，所以测试请**另开一个终端**。

新终端里环境变量是空的，必须重新加载：

```bash
cd /Users/zilongli/Desktop/home/Side-Jobs/AI/mlops-projects/mlops-04-mlflow-production
eval $(floci env)                      # AWS 相关变量
export MASTER_USER=postgres
export MASTER_PW='MasterPw12345'
export PGPASSWORD="$MASTER_PW"
export ARTIFACT_BUCKET=mlflow-artifacts
export MLFLOW_TRACKING_URI=http://localhost:5000
```

> ❗ **忘记 `eval $(floci env)` 是最常见的问题** —— 所有 `aws` 命令会转而打向
> 你的真实 AWS 账号。先验证：
>
> ```bash
> aws sts get-caller-identity --query Account --output text   # 必须是 000000000000
> ```

安装依赖并确认服务在线：

```bash
uv add mlflow scikit-learn
curl -s -o /dev/null -w "MLflow HTTP %{http_code}\n" http://localhost:5000/health   # 期望 200
```

---

## 2. 用例 A — 记录一次真实运行

**目的：** 证明整条链路是通的 —— 客户端 → Pod → PostgreSQL + S3。

```bash
cat > test_a_train.py <<'PY'
import mlflow
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

mlflow.set_experiment("iris-demo")

X, y = load_iris(return_X_y=True)
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

for n in (10, 50, 100):
    with mlflow.start_run(run_name=f"rf-{n}-trees"):
        model = RandomForestClassifier(n_estimators=n, random_state=42).fit(X_tr, y_tr)
        acc = accuracy_score(y_te, model.predict(X_te))

        mlflow.log_param("n_estimators", n)
        mlflow.log_metric("accuracy", acc)
        mlflow.sklearn.log_model(model, name="model")
        print(f"n_estimators={n:3d}  accuracy={acc:.4f}")

print("\n✅ 用例 A 通过 — 打开 http://localhost:5000")
PY

uv run python test_a_train.py
```

**判定通过：** 三次运行都打印出准确率，无报错。实测输出：

```
n_estimators= 10  accuracy=1.0000
n_estimators= 50  accuracy=1.0000
n_estimators=100  accuracy=1.0000
```

> 💡 三次准确率都是 1.0000 是正常的 —— iris 数据集很简单，随机森林轻松做到满分。
> 这不影响测试目的（验证链路通畅）。

### 在界面上确认

1. 打开 **http://localhost:5000**。
2. 左侧边栏 → 实验 **`iris-demo`** → 列出三次运行。
3. 勾选三个 → **Compare** → 看 `n_estimators` 与 `accuracy` 的平行坐标图。
4. 点 **`rf-100-trees`** → **Artifacts** 标签 → `model` 文件夹里有 `MLmodel` 等文件。

---

## 3. 用例 B — 状态存活在外部数据库 ⭐

**这是整套方案的核心测试。** 证明状态在 Floci 管理的数据库里，不在 Pod 里。

### B1. 直接从 PostgreSQL 读数据

MLflow 写进去的，用 `psql` 独立读出来：

```bash
psql -h 127.0.0.1 -p 15432 -U "$MASTER_USER" -d mlflow <<'SQL'
SELECT e.name AS experiment, r.name AS run, m.key, ROUND(m.value::numeric, 4) AS value
FROM runs r
JOIN experiments e ON e.experiment_id = r.experiment_id
JOIN metrics m ON m.run_uuid = r.run_uuid
WHERE e.name = 'iris-demo'
ORDER BY r.name;
SQL
```

**判定通过：** 准确率数值出现在查询结果里。实测：

```
 experiment |     run      |   key    | value
------------+--------------+----------+--------
 iris-demo  | rf-10-trees  | accuracy | 1.0000
 iris-demo  | rf-100-trees | accuracy | 1.0000
 iris-demo  | rf-50-trees  | accuracy | 1.0000
```

> 🔁 注意两条路径汇聚到同一个数据库：Pod 通过 `172.19.0.4:7001` 写入，
> 你通过 `127.0.0.1:15432` 读取。同一个 PostgreSQL，两条路由。
> **界面只是这张表的一个视图。**

### B2. 删掉 Pod —— 数据必须存活

```bash
kubectl delete pod -n mlflow -l app.kubernetes.io/name=mlflow
kubectl rollout status deployment/mlflow -n mlflow      # 等新 Pod 就绪
```

端口转发会随旧 Pod 一起断开，需要重启（在原来那个终端）：

```bash
kubectl port-forward -n mlflow svc/mlflow 5000:80
```

刷新 **http://localhost:5000** → **三次运行记录都还在。**

> ✅ **实测通过。** 删除前后各查一次数据库，运行记录都是 **3 条**；
> 新 Pod 拉起后 `/health` 返回 200，API 也能正常读到 `iris-demo` 实验。
>
> ⚠️ **端口转发一定会断。** 它绑定在被删掉的那个 Pod 上，
> 所以删 Pod 后必须重新执行 `kubectl port-forward`，否则界面打不开。

### B3. 缩容到 0 再恢复 —— 最有说服力的一步

```bash
kubectl scale deployment/mlflow -n mlflow --replicas=0
kubectl get pods -n mlflow          # 一个 Pod 都没有
```

MLflow 完全不存在的情况下，数据依然可查：

```bash
psql -h 127.0.0.1 -p 15432 -U "$MASTER_USER" -d mlflow \
  -c "SELECT COUNT(*) AS 存活的运行数 FROM runs;"
```

```bash
kubectl scale deployment/mlflow -n mlflow --replicas=1
kubectl rollout status deployment/mlflow -n mlflow
kubectl port-forward -n mlflow svc/mlflow 5000:80      # 重启转发
```

**判定通过：** **0 个 Pod** 运行时，运行记录数量不变（应为 3）。

> ✅ **实测通过 —— 这是最有力的一条证据。** 缩容后：
>
> ```
> $ kubectl get pods -n mlflow
> No resources found in mlflow namespace.
>
> $ kubectl get deploy mlflow -n mlflow -o jsonpath='{.spec.replicas} / {.status.readyReplicas}'
> 0 期望 /  就绪
>
> $ psql ... -c "SELECT COUNT(*) FROM runs;"
>      3
> ```
>
> 同时 `curl http://localhost:5000/health` 返回 `HTTP 000`（连不上），
> 证明 MLflow 确实完全不存在 —— 而数据一条没少。
>
> 💡 **数 Pod 时别用 `grep -c`** —— 正在终止（Terminating）的 Pod 也会被算进去，
> 看起来像「还有 1 个」。直接看 `kubectl get pods` 的输出是不是
> `No resources found` 更准确。

```mermaid
sequenceDiagram
    participant U as 你
    participant P as MLflow Pod
    participant R as Floci PostgreSQL

    U->>P: 记录 3 次运行
    P->>R: INSERT runs, metrics
    Note over R: 🟦 状态已持久化
    U->>P: 💥 删除 Pod / 缩容到 0
    Note over P: 算力被销毁
    U->>R: psql SELECT COUNT(*)
    R-->>U: 3 条运行记录 ✅
    Note over U,R: 状态比算力活得更久
```

### B4. 加分项 —— 删掉整个集群

```bash
kind delete cluster --name mlflow-demo
psql -h 127.0.0.1 -p 15432 -U "$MASTER_USER" -d mlflow -c "SELECT COUNT(*) FROM runs;"
```

**判定通过：** 在完全没有 Kubernetes 集群的情况下，运行记录依然存在。

> ⚠️ **这一步会删掉集群。** 想继续测试需要重做
> [搭建篇 §6.1](MLFLOW_生产部署_搭建篇.md#61-创建集群)–[§6.6](MLFLOW_生产部署_搭建篇.md#66-安装)。
> 注意 **§6.2 的 `docker network connect` 必须重做** —— 新集群会创建新的 Docker 网络，
> floci 在 kind 网络里的地址也会变，values 文件里的 `host` 需要相应更新。
>
> **建议把 B4 放在最后做，或者直接跳过。**

---

## 4. 用例 C — 产出文件在 S3 的持久性

用例 B 证明了*元数据*存活。这一步证明**模型文件**同样存活，因为它们存在 Floci 的 S3 里，
而不是 Pod 内部。

### C1. 确认产出文件真的在 S3 里

用例 A 记录了模型。直接看桶 —— MLflow 写进去的，`aws` CLI 独立读出来：

```bash
aws s3 ls "s3://${ARTIFACT_BUCKET}/experiments/" --recursive | head -20
```

实测输出（每个模型 5 个文件）：

```
experiments/1/models/m-62bca5ff.../artifacts/MLmodel            683
experiments/1/models/m-62bca5ff.../artifacts/conda.yaml        2552
experiments/1/models/m-62bca5ff.../artifacts/model.skops     926481
experiments/1/models/m-62bca5ff.../artifacts/python_env.yaml     98
experiments/1/models/m-62bca5ff.../artifacts/requirements.txt  2091
```

```bash
aws s3 ls "s3://${ARTIFACT_BUCKET}" --recursive | wc -l      # 实测：15
```

**判定通过：** 桶里有对象（3 个模型 × 5 个文件 = **15 个**）。

> ### 🔧 实测修正③：不要用 `artifact_location` 判断
>
> **英文原版的判据是**：`artifact_location` 以 `s3://` 开头。**这个判据不成立。**
>
> ```bash
> psql -h 127.0.0.1 -p 15432 -U "$MASTER_USER" -d mlflow \
>   -c "SELECT name, artifact_location FROM experiments;"
> ```
>
> 实测结果：
>
> ```
>    name    |  artifact_location
> -----------+---------------------
>  Default   | mlflow-artifacts:/0
>  iris-demo | mlflow-artifacts:/1
> ```
>
> 这是 `proxiedArtifactStorage: true` 的**正常表现** —— MLflow 3.16 存的是
> **代理 URI**（`mlflow-artifacts:/`），客户端通过 MLflow 服务端读写，
> 由服务端去访问 S3。字节确实在 S3 里（上面 `aws s3 ls` 已证明）。
>
> **所以判据应改为**：用 `aws s3 ls` 确认桶里有对象，而不是看数据库里的 URI 前缀。
> 想看服务端的真实配置：
>
> ```bash
> kubectl get pod -n mlflow -l app.kubernetes.io/name=mlflow \
>   -o jsonpath='{.items[0].spec.containers[0].args}' | tr ',' '\n' | grep artifact
> # 期望：--artifacts-destination=s3://mlflow-artifacts/experiments
> #   以及：--serve-artifacts
> ```

### C2. 删掉 Pod —— 产出文件必须存活

```bash
kubectl delete pod -n mlflow -l app.kubernetes.io/name=mlflow
kubectl rollout status deployment/mlflow -n mlflow
kubectl port-forward -n mlflow svc/mlflow 5000:80
```

在界面里重新打开同一次运行的 **Artifacts** 标签。

**判定通过：** 模型文件**依然列出、依然可下载**。如果不用 S3，
Pod 重启后这个标签页会是空的。

> ✅ **实测通过。** 经过 B2（删 Pod）和 B3（缩容到 0 再恢复）之后，
> Pod 实际已被重建 **2 次**，桶里依然是完整的 **15 个对象**，
> 服务端参数也保持正确：
>
> ```
> --artifacts-destination=s3://mlflow-artifacts/experiments
> --serve-artifacts
> ```

### C3. 通过 MLflow 客户端下载产出文件

> ### 🔧 实测修正④：必须写成脚本文件，不能用 stdin
>
> **不要这样写**（原版写法，会卡住）：
>
> ```bash
> uv run python - <<'PYEOF'    # ❌ 进程挂起，零输出
> ```
>
> 实测现象：进程一直存在，但**一个字节都没输出** —— 连第一行 `import` 都没执行到，
> 而此时 MLflow 服务端是健康的（`/health` 返回 200，Pod 无重启）。
> 问题出在 `uv run` 从 stdin 读取代码时与 heredoc 的配合上，
> **与 C3 本身无关**（下载 3 个文件约 200 KB，正常 1–2 秒完成）。
>
> **正确做法：写成文件再执行。**

```bash
cat > test_c_download.py <<'PY'
import os
import mlflow
from mlflow.tracking import MlflowClient

client = MlflowClient()
exp = client.get_experiment_by_name("iris-demo")
run = client.search_runs([exp.experiment_id], max_results=1)[0]
print("run_id:", run.info.run_id)
path = client.download_artifacts(run.info.run_id, "model")
print("下载到:", path)
print("文件:", sorted(os.listdir(path)))
PY

uv run python test_c_download.py
```

**判定通过：** 文件下载成功。因为 `proxiedArtifactStorage: true`，
这一步在**你的 Mac 上完全不需要任何 S3 配置** —— Pod 从 Floci 取回字节并转发给你。

```mermaid
sequenceDiagram
    participant C as 你的 Mac
    participant P as MLflow Pod
    participant S as Floci S3
    participant R as Floci PostgreSQL

    C->>P: log_model(...)
    P->>R: INSERT 运行元数据
    P->>S: PUT model.skops, MLmodel
    Note over S: 模型字节已持久化
    C->>P: 删除 Pod
    C->>P: （新 Pod）download_artifacts
    P->>R: 查询产出文件位置
    P->>S: GET model.skops
    S-->>P: 字节
    P-->>C: 经 --serve-artifacts 转发
```

**结论：** 元数据在 PostgreSQL + 产出文件在 S3 = **Pod 完全不持有状态**。
这与生产环境的拆分方式完全一致，区别只在端点地址。

> ⚠️ **Floci 的 S3 是内存存储。** `floci stop` 会清空桶，而 PostgreSQL 元数据仍在 ——
> 于是界面上会出现「有运行记录但 Artifacts 为空」。这是模拟器的特性，不是配置错误。

---

## 5. 用例 D — 模型注册表往返

```bash
cat > test_d_registry.py <<'PY'
import mlflow
from mlflow.tracking import MlflowClient

client = MlflowClient()
exp = client.get_experiment_by_name("iris-demo")
best = client.search_runs(
    [exp.experiment_id], order_by=["metrics.accuracy DESC"], max_results=1
)[0]

print(f"最佳运行: {best.info.run_name}  accuracy={best.data.metrics['accuracy']:.4f}")

result = mlflow.register_model(f"runs:/{best.info.run_id}/model", "iris-classifier")
client.set_registered_model_alias("iris-classifier", "champion", result.version)
print(f"✅ 已注册 iris-classifier v{result.version}，别名 'champion'")
PY

uv run python test_d_registry.py
```

在数据库里确认：

```bash
psql -h 127.0.0.1 -p 15432 -U "$MASTER_USER" -d mlflow -c \
  "SELECT name, version, current_stage FROM model_versions;"
```

**在界面上确认：** 顶部导航 → **Models** → **`iris-classifier`** →
版本 1，带 `champion` 别名。

> 💡 别名的价值：代码里可以写 `models:/iris-classifier@champion`，
> 上线换模型时只需把别名指向新版本，代码一行都不用改。
> 详见 [UI 使用指南 §7.2](MLFLOW_UI_使用指南.md#72-版本与别名)。

---

## 6. 结果对照表

| # | 测试 | 判定标准 | 实测结果 |
| --- | --- | --- | --- |
| A | 记录运行 | 界面上 3 次运行，含指标和产出文件 | ✅ **通过** — 3 条记录 + 15 个 S3 对象 |
| B1 | 从 PostgreSQL 读取 | `psql` 返回相同的准确率 | ✅ **通过** — 3 条 accuracy 均为 1.0000 |
| B2 | 删除 Pod | 记录存活，新 Pod 继续提供服务 | ✅ **通过** — 记录仍为 3 条，UI 200 |
| B3 | 缩容到 0 ⭐ | 0 个 Pod 时运行记录数不变 | ✅ **通过** — 0 Pod，记录仍为 3 条 |
| B4 | 删除集群 | 无集群时记录依然存在 | ⬜ 未测（会拆环境） |
| C1/C2 | 产出文件持久性 | **`aws s3 ls` 看到对象**（不是看 `artifact_location`） | ✅ **通过** — 重建 2 次后 15 个对象完好 |
| C3 | 客户端下载 | 文件成功下载到本地 | ⬜ 未测 |
| D | 模型注册表 | 界面和 `model_versions` 表里有 v1 | ⬜ 未测 |

**小结：核心论点已被证实** —— B3 在 0 个 Pod 的情况下数据一条未少，
C1/C2 在 Pod 重建 2 次后产出文件完好。
**状态确实活在集群之外**（元数据在 PostgreSQL，产出文件在 S3）。

---

## 7. 环境清理

这里不产生任何费用，但清理可以释放端口、容器和磁盘。

### 7.1 Kubernetes

```bash
# 先在端口转发那个终端按 Ctrl-C
helm uninstall mlflow -n mlflow
kind delete cluster --name mlflow-demo
```

### 7.2 socat 边车容器

```bash
docker rm -f floci-pg-fwd
```

### 7.3 RDS 实例（命令与真实 AWS 一致）

```bash
aws rds delete-db-instance \
  --db-instance-identifier mlflow-pg \
  --skip-final-snapshot

aws rds describe-db-instances --query 'DBInstances[].DBInstanceIdentifier' --output text
# → 输出为空表示已删除
```

### 7.4 S3 产出文件桶

```bash
aws s3 rm "s3://${ARTIFACT_BUCKET}" --recursive
aws s3 rb "s3://${ARTIFACT_BUCKET}"
aws s3 ls          # 该桶应已消失
```

> ⚠️ **不要删 `wine-dvc-store`** —— 那是
> [DVC 计划](DVC_DATA_VERSIONING_PLAN.md) 参考项目 `mlops-02` 的数据，
> 里面有三个历史版本。

> 删桶会销毁已记录的模型。如果想在拆掉集群后还能查看产出文件，就先别删 —— 不花钱。

### 7.5 可选 —— 断开网络并停止 Floci

```bash
# 如果保留 Floci，把它从 kind 网络断开
docker network disconnect kind floci 2>/dev/null || true

floci stop                      # 停止模拟器（状态会丢失）
# 或者保持运行，只确认状态：
floci status
```

> 删除 kind 集群时那个 Docker 网络本身也会被移除。

### 7.6 本地文件

```bash
rm -f /tmp/mlflow-values.yaml
rm -f test_a_train.py test_c_download.py test_d_registry.py   # 可选：测试脚本
unset PGPASSWORD MASTER_PW MLFLOW_DB_PW PGHOST PGPORT POD_PGHOST FLOCI_IP ARTIFACT_BUCKET
```

### 7.7 确认清理干净

```bash
kind get clusters                  # 不应有 mlflow-demo
docker ps --filter name=floci-pg-fwd    # 应为空
aws rds describe-db-instances --query 'DBInstances[].DBInstanceIdentifier' --output text
aws s3 ls                          # 只剩你自己的桶
```

---

**遇到问题？** 见 [搭建篇 §8 故障排查](MLFLOW_生产部署_搭建篇.md#8-故障排查)。
**看不懂界面？** 见 [MLflow UI 使用指南](MLFLOW_UI_使用指南.md)。
