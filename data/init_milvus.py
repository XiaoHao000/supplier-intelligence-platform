"""
智能旅行助手（Smart Travel）Milvus 初始化脚本
- 创建 smart_travel_docs collection (1024维, COSINE)
- 插入旅游攻略文档种子数据（含 Qwen Embedding 向量）
- docker-compose 启动时自动执行一次

部署步骤：
  1. 确保 MILVUS_HOST/MILVUS_PORT 指向运行中的 Milvus
  2. 确保 API_KEY 已配置（调用 Qwen Embedding API）
  3. python data/init_milvus.py
"""

import json
import os
import sys
import time
import requests

from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility

# Milvus 连接配置
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
COLLECTION_NAME = "smart_travel_docs"
EMBEDDING_DIM = 1024

# Qwen Embedding API
API_KEY = os.getenv("API_KEY", "")
EMBEDDING_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"


def get_embedding(text: str) -> list:
    """调用 Qwen Embedding API 生成 1024 维向量"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "text-embedding-v3",
        "input": [text],
        "dimensions": EMBEDDING_DIM
    }
    response = requests.post(EMBEDDING_URL, headers=headers, json=payload, timeout=30)
    result = response.json()
    return result["data"][0]["embedding"]


# ==================== 旅游攻略文档种子数据 ====================
# content 字段会被 Embedding 编码为向量，用于语义搜索

TRAVEL_DOCS = [
    {
        "trip_id": "TR001",
        "destination": "成都",
        "category": "美食休闲",
        "doc_type": "旅游攻略",
        "rating": 9.5,
        "content": "成都三日游攻略：Day1 宽窄巷子→人民公园喝茶→春熙路太古里逛街→晚上九眼桥酒吧街；Day2 大熊猫繁育研究基地（建议8点前到）→武侯祠→锦里夜市；Day3 都江堰+青城山一日游。必吃：火锅推荐小龙坎、串串香、龙抄手、夫妻肺片、担担面。最佳季节3-6月、9-11月，夏季注意防暑。"
    },
    {
        "trip_id": "TR002",
        "destination": "成都",
        "category": "美食休闲",
        "doc_type": "天气信息",
        "rating": 9.0,
        "content": "成都气候：亚热带湿润季风气候，年均温16°C。春季(3-5月)14-22°C温暖湿润适合出游；夏季(6-8月)25-32°C闷热多雨常有雷阵雨需带雨具；秋季(9-11月)15-24°C秋高气爽最佳旅游季节满城银杏金黄；冬季(12-2月)5-12°C阴冷潮湿少见阳光。全年日照少故有'蜀犬吠日'之说，紫外线弱。"
    },
    {
        "trip_id": "TR003",
        "destination": "三亚",
        "category": "海岛度假",
        "doc_type": "旅游攻略",
        "rating": 9.4,
        "content": "三亚五天四晚度假攻略：Day1 抵达三亚凤凰机场→入住亚龙湾/海棠湾酒店→海滩休闲；Day2 蜈支洲岛一日游（潜水/摩托艇/拖伞）→晚上第一市场海鲜；Day3 南山文化旅游区（108米海上观音）→天涯海角→椰梦长廊看日落；Day4 呀诺达热带雨林→槟榔谷黎苗文化区；Day5 免税店购物→返程。最佳季节11月-次年4月，避开台风季7-9月。"
    },
    {
        "trip_id": "TR004",
        "destination": "三亚",
        "category": "海岛度假",
        "doc_type": "天气信息",
        "rating": 9.2,
        "content": "三亚气候：热带海洋性季风气候，年均温25.7°C，全年无冬。冬季(12-2月)21-28°C温暖干燥旺季机票酒店贵需提前预订；春季(3-5月)24-31°C舒适宜人；夏季(6-8月)27-33°C炎热潮湿偶有台风注意天气预报；秋季(9-11月)25-31°C9月仍多台风10月后逐渐稳定。全年适合下海游泳，紫外线强需做好防晒。"
    },
    {
        "trip_id": "TR005",
        "destination": "丽江",
        "category": "古城文化",
        "doc_type": "综合攻略",
        "rating": 9.7,
        "content": "丽江大理六日深度游：丽江段Day1-3 束河古镇（比大研安静）→玉龙雪山（大索道需提前抢票，4680米注意高反）→蓝月谷→丽江千古情演出→大研古城四方街→狮子山观全景；大理段Day4-6 洱海环湖（租车或电瓶车全程约130km）→双廊古镇→喜洲古镇（白族扎染体验）→苍山索道→崇圣寺三塔。最佳季节4-5月、9-10月避开暑期雨季。海拔2400米，建议带防晒和薄外套。"
    },
    {
        "trip_id": "TR006",
        "destination": "丽江",
        "category": "古城文化",
        "doc_type": "风险提示",
        "rating": 7.0,
        "content": "丽江旅游注意事项：玉龙雪山旺季大索道票紧张需提前3天在'丽江旅游集团'小程序抢购；海拔4680米可能出现高原反应（头痛、气短），建议提前备氧气瓶和红景天；古城内拉客一日游多为低价购物团慎选；雨季(7-8月)山路可能塌方影响泸沽湖行程；机场距古城30km约40分钟车程。暑期游客爆满，建议错峰出行。"
    },
    {
        "trip_id": "TR007",
        "destination": "西安",
        "category": "历史文化",
        "doc_type": "景点详情",
        "rating": 9.3,
        "content": "西安四日经典线路：Day1 兵马俑（世界第八大奇迹，建议上午早到避开人流）→华清宫→晚上回民街羊肉泡馍；Day2 陕西历史博物馆（免费但需预约）→大雁塔→大唐不夜城夜景（不倒翁小姐姐）；Day3 明城墙骑行（全程约14km）→钟楼鼓楼→永兴坊摔碗酒；Day4 华山一日游（西上北下或西上西下，鹞子翻身和长空栈道挑战）。必吃：肉夹馍、biangbiang面、葫芦鸡、甑糕。"
    },
    {
        "trip_id": "TR008",
        "destination": "西安",
        "category": "历史文化",
        "doc_type": "天气信息",
        "rating": 8.8,
        "content": "西安气候：暖温带半湿润大陆性季风气候，四季分明。春季(3-5月)10-25°C气温波动大偶有沙尘需备口罩；夏季(6-8月)25-38°C高温干燥是中国四大火炉之一注意防暑；秋季(9-11月)12-25°C秋高气爽最佳旅游季节；冬季(12-2月)-5-8°C寒冷干燥有雾霾。全年降水集中在7-9月，户外景点建议避开正午高温时段。"
    },
    {
        "trip_id": "TR009",
        "destination": "张家界",
        "category": "自然风光",
        "doc_type": "景点详情",
        "rating": 9.1,
        "content": "张家界四日深度游：Day1 天门山国家森林公园（世界最长索道、玻璃栈道、99道弯通天大道）；Day2-3 张家界国家森林公园（袁家界阿凡达悬浮山、天子山、金鞭溪徒步、十里画廊）；Day4 张家界大峡谷玻璃桥→黄龙洞。住宿建议住武陵源区离景区近。必去打卡：百龙天梯（世界最高户外电梯326米）、杨家界乌龙寨。国家5A景区，阿凡达取景地。"
    },
    {
        "trip_id": "TR010",
        "destination": "张家界",
        "category": "自然风光",
        "doc_type": "风险提示",
        "rating": 7.5,
        "content": "张家界旅游避坑指南：天门山和大峡谷玻璃桥旺季排队2-3小时，建议买VIP免排队票或工作日前往；景区内猴子较多不要喂食和拿塑料袋（会抢）；金鞭溪全程7.5km徒步需3小时建议穿运动鞋；山上山下温差大需带外套；雨天路滑注意安全部分栈道可能关闭；景区内餐饮贵建议自带干粮。最佳季节4-6月、9-11月，避开春节和国庆黄金周。"
    },
    {
        "trip_id": "TR011",
        "destination": "杭州",
        "category": "休闲度假",
        "doc_type": "旅游攻略",
        "rating": 9.2,
        "content": "杭州三日悠闲游：Day1 西湖环湖（断桥残雪→白堤→苏堤春晓→花港观鱼→雷峰塔→柳浪闻莺）→河坊街南宋御街夜市；Day2 灵隐寺（千年古刹）→飞来峰→梅家坞/龙井村品茶→九溪烟树徒步→钱塘江夜景；Day3 西溪湿地（非诚勿扰拍摄地坐摇橹船）→宋城千古情→返程。必吃：西湖醋鱼、龙井虾仁、东坡肉、片儿川、定胜糕。最佳季节4月（龙井新茶上市）和10月（满城桂花香）。"
    },
    {
        "trip_id": "TR012",
        "destination": "杭州",
        "category": "休闲度假",
        "doc_type": "天气信息",
        "rating": 8.6,
        "content": "杭州气候：亚热带季风气候，四季分明。春季(3-5月)10-25°C温暖但多春雨是'烟雨江南'最佳写照；夏季(6-8月)25-37°C高温闷热常有雷阵雨和梅雨季(6月中旬-7月上旬)湿度大；秋季(9-11月)15-28°C秋高气爽桂花飘香最佳旅游季；冬季(12-2月)0-10°C湿冷偶有雪西湖雪景绝美。全年雨量充沛建议随身带伞。"
    },
]


def create_collection():
    """创建 smart_travel_docs 集合"""
    if utility.has_collection(COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' 已存在，删除重建...")
        utility.drop_collection(COLLECTION_NAME)

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="trip_id", dtype=DataType.VARCHAR, max_length=20),
        FieldSchema(name="destination", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=50),
        FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=50),
        FieldSchema(name="rating", dtype=DataType.FLOAT),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=2000),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
    ]

    schema = CollectionSchema(fields, description="旅游攻略文档库")
    collection = Collection(COLLECTION_NAME, schema)

    # 创建 IVF_FLAT 索引（适合数据量不大的场景）
    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": "COSINE",
        "params": {"nlist": 64}
    }
    collection.create_index("embedding", index_params)
    print(f"Collection '{COLLECTION_NAME}' 创建成功，索引类型: IVF_FLAT + COSINE")


def insert_data():
    """插入旅游攻略文档种子数据（含向量）"""
    if not API_KEY:
        print("ERROR: API_KEY 未设置，无法生成 Embedding")
        print("请设置环境变量: export API_KEY=sk-xxx")
        sys.exit(1)

    collection = Collection(COLLECTION_NAME)

    print(f"开始插入 {len(TRAVEL_DOCS)} 条旅游攻略文档...")

    entities = []
    for i, doc in enumerate(TRAVEL_DOCS):
        print(f"  [{i+1}/{len(TRAVEL_DOCS)}] 生成向量: {doc['destination']} - {doc['doc_type']}...")
        embedding = get_embedding(doc["content"])
        time.sleep(0.5)  # API 限速

        entities.append({
            "trip_id": doc["trip_id"],
            "destination": doc["destination"],
            "category": doc["category"],
            "doc_type": doc["doc_type"],
            "rating": doc["rating"],
            "content": doc["content"],
            "embedding": embedding,
        })

    collection.insert(entities)
    collection.flush()
    print(f"插入完成: {collection.num_entities} 条数据")

    # 加载到内存
    collection.load()
    print(f"Collection 已加载到内存")


def test_search():
    """测试语义搜索"""
    collection = Collection(COLLECTION_NAME)

    test_queries = [
        "适合亲子的海岛度假攻略",
        "成都有什么好吃的推荐",
        "丽江高原反应注意事项",
        "秋天适合去哪里旅游",
    ]

    print("\n=== 语义搜索测试 ===")
    for query in test_queries:
        embedding = get_embedding(query)
        results = collection.search(
            data=[embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 10}},
            limit=3,
            output_fields=["destination", "category", "content"]
        )
        print(f"\n查询: '{query}'")
        for hits in results:
            for hit in hits:
                print(f"  [{hit.distance:.3f}] {hit.entity.get('destination')} - {hit.entity.get('content')[:80]}...")


if __name__ == "__main__":
    print(f"连接 Milvus: {MILVUS_HOST}:{MILVUS_PORT}...")
    connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)

    create_collection()
    insert_data()
    test_search()

    print("\n=== Milvus 初始化完成 ===")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"维度: {EMBEDDING_DIM}")
    print(f"数据量: {Collection(COLLECTION_NAME).num_entities} 条")
