"""
需求：管理智能旅行助手（Smart Travel）项目的配置信息，包括大模型、数据库、日志等配置
思路步骤：
1. 定义项目根目录路径
2. 设置环境变量（生产/测试/开发/预生产）
3. 创建Config类管理所有配置项
4. 配置大模型参数（API地址、密钥、模型名称）
5. 配置数据库参数（主机、用户名、密码、数据库名）
6. 配置日志文件路径
7. 配置票务查询接口地址
8. 配置意图映射字典
9. 实现根据环境获取不同数据库配置的方法
"""

import os
import platform

# 项目根目录
project_root = os.path.dirname(os.path.abspath(__file__))

# 检测是否在 Docker 容器中运行
def is_running_in_docker():
    """检测当前是否在 Docker 容器中运行"""
    # 方法1: 检查 /.dockerenv 文件
    if os.path.exists('/.dockerenv'):
        return True
    # 方法2: 检查 cgroup
    try:
        with open('/proc/1/cgroup', 'rt') as f:
            return 'docker' in f.read()
    except:
        pass
    # 方法3: 检查环境变量
    if os.getenv('RUNNING_IN_DOCKER', '').lower() in ('true', '1', 'yes'):
        return True
    return False

# 根据运行环境设置默认主机地址
IN_DOCKER = is_running_in_docker()
DEFAULT_HOST = 'host.docker.internal' if IN_DOCKER else 'localhost'

# 生产环境
# env = "prod"
# 测试环境
env = "test"


# 开发环境
# env = "dev"
# 预生产环境
# env = "pre_prod"


# 定义配置文件
class Config:

    def __init__(self):
        # 大模型配置
        self.api_key = os.getenv("API_KEY")
        self.llm_config = dict(
            model=os.getenv("LLM_MODEL", "qwen3-max"),  # 使用环境变量，默认 qwen3-max
            api_key=os.getenv("API_KEY"),  # 使用配置中的API密钥
            base_url=os.getenv("BASE_URL"),  # 使用配置中的API基础URL
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),  # 使用环境变量，默认 0.1
            streaming=os.getenv("LLM_STREAMING", "True").lower() == "true",  # 启用流式响应
            extra_body={"enable_thinking": os.getenv("LLM_ENABLE_THINKING", "False").lower() == "true"},
        )

        # 数据库配置（从环境变量读取，自动适配本地/Docker环境）
        self.host = os.getenv("MYSQL_HOST", DEFAULT_HOST)
        self.user = os.getenv("MYSQL_USER", "root")
        self.password = os.getenv("MYSQL_PASSWORD", "12345678")
        self.database = os.getenv("MYSQL_DATABASE", "smart_travel")
        self.port = int(os.getenv("MYSQL_PORT", "3306"))

        # Milvus 向量数据库配置（从环境变量读取，自动适配本地/Docker环境）
        self.milvus_host = os.getenv("MILVUS_HOST", DEFAULT_HOST)
        self.milvus_port = int(os.getenv("MILVUS_PORT", "19530"))

        # 日志配置
        self.log_file = os.path.join(project_root, 'SmartTravel', 'logs/app.log')

        # 票务查询的12306接口地址
        self.url_123 = ""

        self.intent = {
            "weather": "WeatherAgent",
            "ticket": "TicketAgent",
            "trip": "TripAgent",
            "guide": "GuideAgent",
        }

        self.temperature = 0.1

        # 旅行数据源配置
        # 可选值："database"（从数据库获取） / "api"（直接从外部API获取）
        self.data_source = "database"

        # LangSmith 可观测性配置
        self.langsmith_api_key = os.getenv("LANGSMITH_API_KEY", "")
        self.langsmith_project = os.getenv("LANGSMITH_PROJECT", "smart-travel-assistant")
        if self.langsmith_api_key:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self.langsmith_api_key
            os.environ["LANGCHAIN_PROJECT"] = self.langsmith_project

        # Redis 配置（用于演示额度计数器，自动适配本地/Docker）
        self.redis_url = os.getenv("REDIS_URL", f"redis://{DEFAULT_HOST}:6379/0")

        # Demo Budget（演示服务防滥用 — 每个 IP 每天独立额度，用户之间互不影响）
        self.demo_daily_query_limit = int(os.getenv("DEMO_DAILY_QUERY_LIMIT", "30"))

    def get_mysql_config(self, env=None):
        """
        通过不同的环境获取不同的数据库配置
        如果 env 为 None，则使用环境变量中的配置
        :param env: 环境名称 (prod/dev/test/pre_prod)
        :return: host, user, password, database, port
        """
        # 优先使用环境变量配置
        if env is None:
            return (
                os.getenv("MYSQL_HOST", DEFAULT_HOST),
                os.getenv("MYSQL_USER", "root"),
                os.getenv("MYSQL_PASSWORD", "12345678"),
                os.getenv("MYSQL_DATABASE", "smart_travel"),
                int(os.getenv("MYSQL_PORT", "3306"))
            )
        
        # 根据环境返回不同配置（保留原有逻辑，自动适配本地/Docker）
        if env == 'prod':
            self.host = os.getenv("MYSQL_PROD_HOST", DEFAULT_HOST)
            self.user = os.getenv("MYSQL_PROD_USER", "root")
            self.password = os.getenv("MYSQL_PROD_PASSWORD", "root")
            self.database = os.getenv("MYSQL_PROD_DATABASE", "smart_travel")
            self.port = int(os.getenv("MYSQL_PROD_PORT", "3306"))
        elif env == 'dev':
            self.host = os.getenv("MYSQL_DEV_HOST", DEFAULT_HOST)
            self.user = os.getenv("MYSQL_DEV_USER", "root")
            self.password = os.getenv("MYSQL_DEV_PASSWORD", "root")
            self.database = os.getenv("MYSQL_DEV_DATABASE", "smart_travel")
            self.port = int(os.getenv("MYSQL_DEV_PORT", "3306"))
        elif env == 'test':
            self.host = os.getenv("MYSQL_TEST_HOST", DEFAULT_HOST)
            self.user = os.getenv("MYSQL_TEST_USER", "root")
            self.password = os.getenv("MYSQL_TEST_PASSWORD", "root")
            self.database = os.getenv("MYSQL_TEST_DATABASE", "smart_travel")
            self.port = int(os.getenv("MYSQL_TEST_PORT", "3306"))
        else:  # pre_prod
            self.host = os.getenv("MYSQL_PRE_PROD_HOST", DEFAULT_HOST)
            self.user = os.getenv("MYSQL_PRE_PROD_USER", "root")
            self.password = os.getenv("MYSQL_PRE_PROD_PASSWORD", "root")
            self.database = os.getenv("MYSQL_PRE_PROD_DATABASE", "smart_travel")
            self.port = int(os.getenv("MYSQL_PRE_PROD_PORT", "3306"))

        return self.host, self.user, self.password, self.database, self.port


if __name__ == '__main__':
    print(Config().log_file)
    print(Config().get_mysql_config(env))
    # ('localhost', 'root', 'root', 'smart_travel')
    # ('localhost', 'root2', 'root2', 'smart_travel')
