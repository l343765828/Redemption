import redis

# 替换为你的真实 Redis IP 或 Hostname，以及密码（如果有）
client = redis.Redis(host='192.168.18.149', port=36378, db=0, password='123456')

try:
    info = client.info()
    print(f"成功连接！你的 Redis 服务端版本是: {info.get('redis_version')}")

    # 尝试执行一个最基础的 JSON.SET 命令
    client.execute_command('JSON.SET', 'test_json_check', '$', '{"status": "ok"}')
    print("✅ 恭喜！你的 Redis 已成功安装并启用了 RedisJSON 模块。")

    # 测试完顺手清理掉测试数据
    client.delete('test_json_check')
except redis.exceptions.ResponseError as e:
    if "unknown command" in str(e).lower():
        print("❌ 验证失败：你的 Redis 没有安装 RedisJSON 模块。")
    else:
        print(f"⚠️ 连接成功，但出现其他错误: {e}")
except redis.exceptions.ConnectionError as e:
    print(f"连接失败，请检查网络或配置: {e}")