import { FlatTask, Category, AlertSettings } from '../types';

const TASKS_KEY = 'taskflow_tasks';
const CATEGORIES_KEY = 'taskflow_categories';
const SETTINGS_KEY = 'taskflow_settings';

export const loadTasks = (): FlatTask[] => {
  try {
    const data = localStorage.getItem(TASKS_KEY);
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
};

export const saveTasks = (tasks: FlatTask[]): void => {
  localStorage.setItem(TASKS_KEY, JSON.stringify(tasks));
};

export const loadCategories = (): Category[] => {
  try {
    const data = localStorage.getItem(CATEGORIES_KEY);
    return data ? JSON.parse(data) : getDefaultCategories();
  } catch {
    return getDefaultCategories();
  }
};

export const saveCategories = (categories: Category[]): void => {
  localStorage.setItem(CATEGORIES_KEY, JSON.stringify(categories));
};

export const loadSettings = (): AlertSettings => {
  try {
    const data = localStorage.getItem(SETTINGS_KEY);
    return data ? JSON.parse(data) : getDefaultSettings();
  } catch {
    return getDefaultSettings();
  }
};

export const saveSettings = (settings: AlertSettings): void => {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
};

const getDefaultCategories = (): Category[] => [
  { id: 'cat-1', name: '仕事', color: '#3B82F6' },
  { id: 'cat-2', name: '個人', color: '#10B981' },
  { id: 'cat-3', name: '学習', color: '#8B5CF6' },
];

const getDefaultSettings = (): AlertSettings => ({
  warningDays: 3,
  showBanner: true,
  browserNotifications: false,
});
