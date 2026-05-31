import { DeadlineStatus } from '../types';

export const getDeadlineStatus = (dueDate?: string): DeadlineStatus => {
  if (!dueDate) return 'ok';

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dueDate);
  due.setHours(0, 0, 0, 0);
  const diff = Math.round((due.getTime() - today.getTime()) / 86400000);

  if (diff < 0) return 'overdue';
  if (diff === 0) return 'today';
  if (diff === 1) return 'tomorrow';
  if (diff <= 3) return 'soon';
  return 'ok';
};

export const getDaysRemaining = (dueDate?: string): number | null => {
  if (!dueDate) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dueDate);
  due.setHours(0, 0, 0, 0);
  return Math.round((due.getTime() - today.getTime()) / 86400000);
};

export const getDeadlineColorHex = (status: DeadlineStatus): string => {
  switch (status) {
    case 'overdue': return '#EF4444';
    case 'today': return '#F97316';
    case 'tomorrow': return '#EAB308';
    case 'soon': return '#3B82F6';
    default: return '#6B7280';
  }
};

export const getDeadlineBgClass = (status: DeadlineStatus): string => {
  switch (status) {
    case 'overdue': return 'bg-red-50 dark:bg-red-900/20 border-l-4 border-l-red-500';
    case 'today': return 'bg-orange-50 dark:bg-orange-900/20 border-l-4 border-l-orange-500';
    case 'tomorrow': return 'bg-yellow-50 dark:bg-yellow-900/20 border-l-4 border-l-yellow-500';
    case 'soon': return 'bg-blue-50 dark:bg-blue-900/20 border-l-4 border-l-blue-500';
    default: return '';
  }
};

export const formatDeadlineBadge = (dueDate?: string): string => {
  const days = getDaysRemaining(dueDate);
  if (days === null) return '';
  if (days < 0) return `${Math.abs(days)}日超過`;
  if (days === 0) return '今日まで';
  if (days === 1) return '明日まで';
  return `残り${days}日`;
};

export const getDeadlineBadgeClass = (status: DeadlineStatus): string => {
  switch (status) {
    case 'overdue': return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
    case 'today': return 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300 animate-pulse-slow';
    case 'tomorrow': return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300';
    case 'soon': return 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300';
    default: return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
  }
};
