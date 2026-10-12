import axios from 'axios';

const rawBase = import.meta.env.VITE_API_BASE_URL || '';
const cleanBase = rawBase.replace(/\/+$/, '');
const fullBase = cleanBase
  ? (cleanBase.endsWith('/api/v1') ? cleanBase : `${cleanBase}/api/v1`)
  : '/api/v1';

export const apiClient = axios.create({
  baseURL: fullBase,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 20000, // 20s timeout
});
