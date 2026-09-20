import json

from backend.app import create_app
from backend.database import get_engine
from backend.migrations.runner import migrate


if __name__ == "__main__":
    # 导入应用以登记全部数据模型；CLI 不启动服务或调用模型。
    create_app(initialize_database=False)
    print(json.dumps(migrate(get_engine()), ensure_ascii=False))
