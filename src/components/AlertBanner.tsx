import React, { useState } from 'react';
import { X, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react';
import { FlatTask, Category } from '../types';
import { getDeadlineStatus } from '../utils/deadlineUtils';
import { formatDateShort } from '../utils/timeUtils';

interface AlertBannerProps {
  tasks: FlatTask[];
  categories: Category[];
  onTaskClick: (id: string) => void;
}

const AlertBanner: React.FC<AlertBannerProps> = ({ tasks, categories, onTaskClick }) => {
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const catMap = Object.fromEntries(categories.map(c => [c.id, c]));

  const overdue = tasks.filter(t => t.status !== 'done' && getDeadlineStatus(t.dueDate) === 'overdue');
  const today = tasks.filter(t => t.status !== 'done' && getDeadlineStatus(t.dueDate) === 'today');
  const tomorrow = tasks.filter(t => t.status !== 'done' && getDeadlineStatus(t.dueDate) === 'tomorrow');

  if ((overdue.length + today.length + tomorrow.length) === 0) return null;
  if (dismissed) return (
    <div className="flex justify-end px-4 pt-2">
      <button
        onClick={() => setDismissed(false)}
        className="flex items-center gap-1.5 text-xs text-orange-600 dark:text-orange-400 hover:underline"
      >
        <AlertTriangle size={12} />
        期限アラートを表示
      </button>
    </div>
  );

  const alertTasks = [...overdue, ...today, ...tomorrow];

  return (
    <div className="bg-amber-50 dark:bg-amber-900/20 border-b border-amber-200 dark:border-amber-800">
      <div className="flex items-center gap-3 px-4 py-2.5">
        <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 flex-shrink-0" />
        <div className="flex items-center gap-3 flex-1 flex-wrap">
          {overdue.length > 0 && (
            <span className="text-sm font-medium text-red-600 dark:text-red-400">
              🔴 期限切れ {overdue.length}件
            </span>
          )}
          {today.length > 0 && (
            <span className="text-sm font-medium text-orange-600 dark:text-orange-400">
              🟠 今日期限 {today.length}件
            </span>
          )}
          {tomorrow.length > 0 && (
            <span className="text-sm font-medium text-yellow-600 dark:text-yellow-400">
              🟡 明日期限 {tomorrow.length}件
            </span>
          )}
        </div>
        <button
          onClick={() => setExpanded(e => !e)}
          className="flex items-center gap-1 text-xs text-amber-700 dark:text-amber-300 hover:text-amber-900 dark:hover:text-amber-100 transition-colors"
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {expanded ? '閉じる' : '詳細'}
        </button>
        <button
          onClick={() => setDismissed(true)}
          className="text-amber-600 hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-200 transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      {expanded && (
        <div className="px-4 pb-3 space-y-1 animate-fade-in">
          {alertTasks.map(task => {
            const status = getDeadlineStatus(task.dueDate);
            const cat = catMap[task.categoryId];
            const colorClass = status === 'overdue' ? 'text-red-600 dark:text-red-400' :
              status === 'today' ? 'text-orange-600 dark:text-orange-400' :
              'text-yellow-600 dark:text-yellow-400';
            return (
              <button
                key={task.id}
                onClick={() => onTaskClick(task.id)}
                className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-800/30 text-left transition-colors"
              >
                {cat && <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: cat.color }} />}
                <span className="flex-1 text-sm text-gray-800 dark:text-gray-200 truncate">{task.title}</span>
                <span className={`text-xs font-medium ${colorClass}`}>
                  {task.dueDate && formatDateShort(task.dueDate)}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default AlertBanner;
