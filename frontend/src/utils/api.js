/**
 * Safe fetch utility to parse JSON responses without throwing 'Unexpected end of JSON input'
 */
export const safeFetchJson = async (url, options = {}) => {
  const res = await fetch(url, options);
  const text = await res.text();
  let data = {};
  if (text && text.trim()) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: `Server response (${res.status}): Invalid or non-JSON response.` };
    }
  }
  if (!res.ok) {
    throw new Error(data.detail || `Request failed with status ${res.status}`);
  }
  return data;
};
