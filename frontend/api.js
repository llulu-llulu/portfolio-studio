/** Same-origin API; callers commit state only after a successful response. */
export async function api(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  try {
    const options = { signal: controller.signal };
    if (body !== undefined) {
      Object.assign(options, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    }
    const response = await fetch(`/api${path}`, options);
    let data;
    try {
      data = await response.json();
    } catch (error) {
      if (controller.signal.aborted) throw error;
      throw new Error(response.ok
        ? '返回的数据暂时无法读取，请重试。已有模拟结果已保留。'
        : `服务暂时不可用（${response.status}），请稍后重试。已有模拟结果已保留。`);
    }
    if (!response.ok) {
      throw new Error(data.error?.message || `服务暂时不可用（${response.status}），请稍后重试。`);
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('请求超时，请重试。已有模拟结果已保留。');
    if (error instanceof TypeError) throw new Error('无法连接本地服务，请确认服务已启动后重试。');
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
