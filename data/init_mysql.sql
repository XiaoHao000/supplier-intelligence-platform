-- ============================================================
-- 智能旅行助手（Smart Travel Assistant）MySQL 初始化脚本
-- 建库建表 + 种子数据
-- 通过 docker-compose 的 docker-entrypoint-initdb.d 自动执行
-- ============================================================

-- ==================== 记忆相关表 ====================

CREATE TABLE IF NOT EXISTS user_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    profile_key VARCHAR(100) NOT NULL COMMENT '偏好键',
    profile_value TEXT COMMENT '偏好值',
    UNIQUE KEY uk_key (profile_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户偏好';

CREATE TABLE IF NOT EXISTS query_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    intent_type VARCHAR(50) COMMENT '意图类型',
    query_content TEXT COMMENT '查询内容',
    query_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '查询时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='查询历史';

CREATE TABLE IF NOT EXISTS short_term_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    role VARCHAR(20) NOT NULL COMMENT '角色(user/assistant)',
    content TEXT NOT NULL COMMENT '消息内容',
    message_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '消息时间',
    message_order INT DEFAULT 0 COMMENT '消息顺序'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短期对话记忆';

-- ==================== 旅游信息表 ====================

CREATE TABLE IF NOT EXISTS travel_info (
    id INT AUTO_INCREMENT PRIMARY KEY,
    destination VARCHAR(100) NOT NULL COMMENT '目的地名称',
    info_type VARCHAR(50) NOT NULL COMMENT '信息类型(景区评级/天气信息/最佳季节/特色亮点)',
    info_code VARCHAR(100) COMMENT '信息编号',
    source_authority VARCHAR(200) COMMENT '信息来源',
    issue_date DATE COMMENT '发布日期',
    expiry_date DATE COMMENT '截止日期',
    status VARCHAR(20) DEFAULT '有效' COMMENT '状态(有效/即将更新/已过期)',
    info_scope TEXT COMMENT '详细信息'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='目的地旅游信息';

INSERT INTO travel_info (destination, info_type, info_code, source_authority, issue_date, expiry_date, status, info_scope) VALUES
('成都', '景区评级AAAAA', 'AAAAA-CDU-2023001', '文化和旅游部', '2023-03-15', '2026-03-14', '有效', '青城山-都江堰风景名胜区，世界文化遗产，国家级风景名胜区'),
('成都', '国家级风景名胜区', 'NSCA-CDU-2024001', '国务院', '2024-01-10', '2027-01-09', '有效', '大熊猫栖息地世界自然遗产，西岭雪山国家级风景名胜区'),
('成都', '最佳旅游季节', 'SEASON-CDU-2024', '成都市文旅局', '2024-03-01', '2025-03-01', '有效', '最佳旅游季节3-6月、9-11月，春秋气候宜人，夏季注意防暑'),
('西安', '景区评级AAAAA', 'AAAAA-XA-2022008', '文化和旅游部', '2022-06-01', '2025-05-31', '即将到期', '秦始皇陵及兵马俑，世界文化遗产，国家AAAAA级景区'),
('西安', '国家历史文化名城', 'NHCC-XA-2023105', '国务院', '2023-09-15', '2028-09-14', '有效', '中国四大古都之一，丝绸之路起点，历史文化名城'),
('三亚', '景区评级AAAAA', 'AAAAA-SY-2023003', '文化和旅游部', '2023-05-10', '2026-05-09', '有效', '南山文化旅游区，天涯海角风景名胜区，蜈支洲岛旅游区'),
('三亚', '国家旅游度假区', 'NTRZ-SY-2024010', '文化和旅游部', '2024-01-10', '2025-06-30', '即将到期', '亚龙湾国家旅游度假区，海棠湾国家海岸'),
('丽江', '景区评级AAAAA', 'AAAAA-LJ-2023005', '文化和旅游部', '2023-08-01', '2026-07-31', '有效', '丽江古城世界文化遗产，玉龙雪山国家风景名胜区'),
('丽江', '国家级风景名胜区', 'NSCA-LJ-2023002', '国务院', '2023-08-15', '2026-08-14', '有效', '玉龙雪山、泸沽湖、老君山三大国家级风景名胜区'),
('丽江', '世界文化遗产', 'WHC-LJ-2024005', '联合国教科文组织', '2023-10-15', '2026-10-14', '有效', '丽江古城列入世界文化遗产名录，纳西族东巴文化'),
('张家界', '景区评级AAAAA', 'AAAAA-ZJJ-2024002', '文化和旅游部', '2024-02-01', '2027-01-31', '有效', '武陵源风景名胜区世界自然遗产，天门山国家森林公园'),
('张家界', '世界自然遗产', 'WNH-ZJJ-20231002', '联合国教科文组织', '2023-12-01', '2028-11-30', '有效', '武陵源砂岩峰林地貌，世界罕见的石英砂岩峰林峡谷地貌'),
('杭州', '景区评级AAAAA', 'AAAAA-HZ-2023006', '文化和旅游部', '2023-04-20', '2026-04-19', '有效', '西湖风景名胜区世界文化景观遗产，西溪国家湿地公园'),
('北京', '景区评级AAAAA', 'AAAAA-BJ-2024001', '文化和旅游部', '2024-01-01', '2026-12-31', '有效', '故宫博物院、八达岭长城、颐和园、天坛公园等'),
('桂林', '景区评级AAAAA', 'AAAAA-GL-2023002', '文化和旅游部', '2023-07-01', '2026-06-30', '有效', '漓江风景名胜区，世界自然遗产，桂林山水甲天下'),
('桂林', '国家级风景名胜区', 'NSCA-GL-2024003', '国务院', '2023-09-01', '2026-08-31', '有效', '桂林漓江国家级风景名胜区，喀斯特地貌世界遗产');

-- ==================== 航班票务表 ====================

CREATE TABLE IF NOT EXISTS flight_tickets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    destination VARCHAR(100) NOT NULL COMMENT '目的地',
    flight_number VARCHAR(50) NOT NULL COMMENT '航班号',
    flight_name VARCHAR(200) COMMENT '航空公司/航班名称',
    ticket_price DECIMAL(10,2) COMMENT '票价(元)',
    departure_date DATE COMMENT '计划出发日期',
    actual_departure_date DATE COMMENT '实际出发日期',
    available_seats INT COMMENT '余票数量',
    change_cancel_rate DECIMAL(5,2) COMMENT '退改签率(%)',
    service_score DECIMAL(3,1) COMMENT '服务评分(1-10)',
    on_time_departure BOOLEAN DEFAULT TRUE COMMENT '是否准点起飞',
    user_rating DECIMAL(3,1) COMMENT '用户评分(1-10)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='航班票务信息';

INSERT INTO flight_tickets (destination, flight_number, flight_name, ticket_price, departure_date, actual_departure_date, available_seats, change_cancel_rate, service_score, on_time_departure, user_rating) VALUES
('成都', 'CA1401', '中国国航', 1280.00, '2024-03-15', '2024-03-14', 120, 5.2, 9.5, TRUE, 9.2),
('成都', 'MU5401', '东方航空', 1050.00, '2024-05-20', '2024-05-18', 85, 3.8, 9.7, TRUE, 9.5),
('成都', 'CZ8801', '南方航空', 960.00, '2024-07-01', '2024-07-03', 200, 6.1, 9.3, FALSE, 8.8),
('西安', 'CA1201', '中国国航', 890.00, '2024-02-10', '2024-02-09', 150, 4.5, 9.0, TRUE, 8.9),
('西安', 'MU2101', '东方航空', 750.00, '2024-09-15', '2024-09-20', 95, 7.2, 8.5, FALSE, 8.2),
('三亚', 'CZ6701', '南方航空', 1860.00, '2024-01-05', '2024-01-04', 60, 3.0, 9.8, TRUE, 9.6),
('三亚', 'HU7601', '海南航空', 1580.00, '2024-04-20', '2024-04-22', 110, 4.1, 9.4, FALSE, 9.0),
('丽江', 'MU5801', '东方航空', 1350.00, '2024-03-01', '2024-02-28', 75, 2.5, 9.9, TRUE, 9.7),
('丽江', 'CZ3401', '南方航空', 1120.00, '2024-06-15', '2024-06-15', 130, 3.2, 9.6, TRUE, 9.4),
('张家界', 'CZ3101', '南方航空', 980.00, '2024-05-10', '2024-05-12', 85, 5.0, 9.2, FALSE, 8.7),
('杭州', 'CA1701', '中国国航', 1150.00, '2024-08-01', '2024-07-30', 140, 3.5, 9.5, TRUE, 9.3),
('杭州', 'MF8501', '厦门航空', 920.00, '2024-04-01', '2024-03-31', 100, 4.8, 9.4, TRUE, 9.1),
('北京', 'CA1501', '中国国航', 1350.00, '2024-09-01', '2024-09-10', 180, 8.5, 7.8, FALSE, 7.5),
('桂林', 'CZ3201', '南方航空', 780.00, '2024-07-20', '2024-07-18', 90, 3.9, 9.1, TRUE, 8.9),
('昆明', 'MU5701', '东方航空', 1050.00, '2024-06-01', '2024-06-01', 120, 2.8, 9.8, TRUE, 9.5);

-- ==================== 旅游动态/新闻表 ====================

CREATE TABLE IF NOT EXISTS travel_news (
    id INT AUTO_INCREMENT PRIMARY KEY,
    destination VARCHAR(100) NOT NULL COMMENT '目的地名称',
    source VARCHAR(50) COMMENT '来源(新闻/社交/攻略/公告)',
    title VARCHAR(500) COMMENT '标题',
    content TEXT COMMENT '内容摘要',
    sentiment VARCHAR(10) COMMENT '情感(正面/中性/负面)',
    risk_level VARCHAR(10) COMMENT '风险等级(高/中/低)',
    publish_date DATE COMMENT '发布日期',
    url VARCHAR(500) COMMENT '来源链接',
    keywords VARCHAR(500) COMMENT '关键词'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='旅游新闻动态';

INSERT INTO travel_news (destination, source, title, content, sentiment, risk_level, publish_date, url, keywords) VALUES
('成都', '新闻', '成都发布2024年度旅游发展报告', '成都发布2024年度旅游发展报告，全面展示在智慧旅游、生态旅游、文化旅游等方面的进展。成都全年接待游客超过2.8亿人次。', '正面', '低', '2024-03-28', 'https://example.com/chengdu-tourism-2024', '旅游发展,智慧旅游,生态旅游'),
('成都', '新闻', '成都位列国内热门旅游目的地前三', '据行业报告显示，成都2024年Q1位列国内热门旅游目的地前三名，美食和熊猫是主要吸引力。', '正面', '低', '2024-04-15', 'https://example.com/chengdu-top3', '热门目的地,美食,大熊猫'),
('成都', '社交', '部分游客反映大熊猫基地排队时间过长', '有游客在社交媒体反映成都大熊猫繁育研究基地旺季排队超过2小时，建议提前预约和错峰出行。', '负面', '中', '2024-05-10', 'https://example.com/panda-queue', '排队,大熊猫基地,错峰'),
('西安', '新闻', '西安大唐不夜城入选夜间文旅消费集聚区', '西安大唐不夜城成功入选国家级夜间文化和旅游消费集聚区，春节期间日均客流超过60万人次。', '正面', '低', '2024-02-20', 'https://example.com/xian-night-tourism', '夜间经济,大唐不夜城,文旅消费'),
('西安', '公告', '陕西历史博物馆启用新预约系统', '陕西历史博物馆宣布启用新的实名制预约系统，每日限量12000张免费门票，需提前7天预约。', '中性', '中', '2024-04-01', 'https://example.com/xian-museum-booking', '预约,博物馆,实名制'),
('三亚', '新闻', '三亚春节期间游客量创历史新高', '三亚2024年春节期间接待游客超过150万人次，旅游收入突破100亿元，免税购物成为重要增长点。', '正面', '低', '2024-02-10', 'https://example.com/sanya-spring-festival', '春节,游客量,免税购物,增长'),
('三亚', '社交', '网友热议三亚海鲜宰客问题', '社交媒体上有游客反映三亚部分海鲜排档存在宰客现象，价格明显高于市区，建议去第一市场自选加工。', '负面', '中', '2024-01-25', 'https://example.com/sanya-seafood-price', '海鲜,宰客,消费投诉,游客反馈'),
('三亚', '新闻', '三亚入选中国十佳旅游城市', '中国旅游研究院发布2024中国十佳旅游城市榜单，三亚连续第五年入选，排名第三。', '正面', '低', '2024-05-03', 'https://example.com/sanya-top10', '十佳旅游城市,排名,旅游研究院'),
('丽江', '攻略', '丽江古城保护管理局发布限流公告', '丽江古城保护管理局宣布旺季将实施限流措施，每日最大承载量为15万人次，建议游客提前预约。', '中性', '中', '2024-04-18', 'https://example.com/lijiang-crowd-control', '限流,古城保护,预约'),
('丽江', '新闻', '丽江至大理高铁开通运营', '丽江至大理高速铁路正式开通运营，全程仅需1.5小时，极大便利了滇西旅游出行。', '正面', '低', '2024-03-15', 'https://example.com/lijiang-dali-highspeed', '高铁,大理,交通,便利'),
('张家界', '新闻', '张家界入选全球十大自然奇观', '国际知名旅游杂志评选张家界为全球十大自然奇观之一，阿凡达取景地再次引发全球关注。', '正面', '低', '2024-05-08', 'https://example.com/zhangjiajie-top10', '自然奇观,阿凡达,国际认可'),
('杭州', '社交', '西湖景区节假日人流量过大引担忧', '部分游客和媒体关注西湖景区节假日人流量过大问题，断桥和苏堤区域尤为拥挤，建议工作日前往。', '负面', '中', '2024-04-22', 'https://example.com/hangzhou-westlake-crowd', '西湖,人流,拥挤,节假日'),
('北京', '公告', '故宫博物院暑期延长开放时间', '故宫博物院宣布暑期（7-8月）延长开放时间至晚8点，并增加夜场参观场次，需单独预约。', '正面', '低', '2024-06-01', 'https://example.com/forbidden-city-summer', '故宫,延长开放,暑期,夜场'),
('桂林', '新闻', '桂林漓江水位下降影响游船运营', '受持续干旱影响，桂林漓江部分河段水位下降，大船需改为竹筏游览，游客体验可能受影响。', '负面', '中', '2024-03-30', 'https://example.com/guilin-water-level', '漓江,水位,干旱,游船影响');

-- ==================== 旅游风险提示表 ====================

CREATE TABLE IF NOT EXISTS travel_advisories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    destination VARCHAR(100) NOT NULL COMMENT '目的地名称',
    advisory_type VARCHAR(50) COMMENT '提示类型(天气/安全/交通/健康/政策)',
    advisory_level VARCHAR(10) COMMENT '预警等级(红/橙/黄)',
    description TEXT COMMENT '提示描述',
    trigger_date DATE COMMENT '发布日期',
    status VARCHAR(20) DEFAULT '活跃' COMMENT '状态',
    suggestion TEXT COMMENT '出行建议'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='旅游风险提示';

INSERT INTO travel_advisories (destination, advisory_type, advisory_level, description, trigger_date, status, suggestion) VALUES
('西安', '天气', '红', '夏季高温预警持续，7-8月最高温可达38°C以上，户外景点游览体验下降。', '2024-07-01', '活跃', '建议：1)避免正午户外活动 2)选择室内景点 3)携带充足饮用水和防晒用品'),
('三亚', '安全', '橙', '台风季预警，7-9月为台风高发期，部分海上项目可能暂停，需关注天气预报。', '2024-07-15', '活跃', '建议：1)购买旅游保险 2)关注台风路径 3)预留行程弹性时间'),
('丽江', '健康', '橙', '玉龙雪山高海拔区域（4680m）可能出现高原反应，部分游客出现头痛、气短等症状。', '2024-04-01', '活跃', '建议：1)提前备氧气瓶 2)服用红景天 3)缓慢登山逐步适应 4)有心脏病史游客谨慎前往'),
('桂林', '天气', '黄', '漓江枯水期持续，水位偏低影响部分航段游船运营，竹筏体验正常。', '2024-03-30', '活跃', '建议：1)选择竹筏游览替代大船 2)关注水文信息 3)预留备选行程'),
('张家界', '安全', '黄', '部分玻璃栈道和悬崖步道雨天湿滑，可能临时关闭，需关注景区公告。', '2024-05-01', '活跃', '建议：1)雨天谨慎前往高空项目 2)穿防滑鞋 3)提前查看景区开放信息'),
('成都', '天气', '黄', '夏季雷阵雨频繁，都江堰、青城山区域偶有山洪预警，不建议雨天溯溪。', '2024-06-01', '活跃', '建议：1)携带雨具 2)关注山洪预警 3)避开河道区域'),
('杭州', '安全', '黄', '西湖音乐喷泉因设备检修暂时关闭，预计2024年8月恢复，具体时间待定。', '2024-07-01', '活跃', '建议：1)调整行程安排 2)选择印象西湖演出作为替代');

-- ==================== 目的地口碑评分表 ====================

CREATE TABLE IF NOT EXISTS destination_ratings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    destination VARCHAR(100) NOT NULL COMMENT '目的地名称',
    period VARCHAR(20) COMMENT '统计周期',
    positive_ratio DECIMAL(5,2) COMMENT '正面比例(%)',
    negative_ratio DECIMAL(5,2) COMMENT '负面比例(%)',
    neutral_ratio DECIMAL(5,2) COMMENT '中性比例(%)',
    overall_score DECIMAL(3,1) COMMENT '综合口碑分(1-10)',
    trending VARCHAR(10) COMMENT '趋势(上升/下降/平稳)',
    sample_count INT COMMENT '样本数',
    update_time DATE COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='目的地口碑评分统计';

INSERT INTO destination_ratings (destination, period, positive_ratio, negative_ratio, neutral_ratio, overall_score, trending, sample_count, update_time) VALUES
('成都', '2025Q1', 85.50, 5.30, 9.20, 9.0, '平稳', 12450, '2025-04-01'),
('成都', '2025Q2', 86.10, 4.80, 9.10, 9.1, '上升', 13890, '2025-07-01'),
('西安', '2025Q1', 82.20, 7.50, 10.30, 8.7, '上升', 8950, '2025-04-01'),
('西安', '2025Q2', 83.10, 6.80, 10.10, 8.8, '上升', 9450, '2025-07-01'),
('三亚', '2025Q1', 78.30, 9.10, 12.60, 8.3, '平稳', 15600, '2025-04-01'),
('三亚', '2025Q2', 76.50, 10.20, 13.30, 8.1, '下降', 16200, '2025-07-01'),
('丽江', '2025Q1', 88.20, 3.50, 8.30, 9.2, '平稳', 7980, '2025-04-01'),
('丽江', '2025Q2', 89.50, 3.20, 7.30, 9.3, '上升', 8400, '2025-07-01'),
('张家界', '2025Q1', 84.00, 5.50, 10.50, 8.8, '平稳', 6890, '2025-04-01'),
('张家界', '2025Q2', 85.50, 4.80, 9.70, 9.0, '上升', 7200, '2025-07-01'),
('杭州', '2025Q1', 86.50, 5.20, 8.30, 8.9, '平稳', 10200, '2025-04-01'),
('杭州', '2025Q2', 87.00, 4.50, 8.50, 9.0, '上升', 10500, '2025-07-01'),
('北京', '2025Q1', 82.50, 8.00, 9.50, 8.5, '平稳', 18600, '2025-04-01'),
('桂林', '2025Q1', 80.10, 6.50, 13.40, 8.4, '平稳', 5600, '2025-04-01'),
('昆明', '2025Q1', 83.50, 5.50, 11.00, 8.7, '上升', 7200, '2025-04-01');
