import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Clock } from 'lucide-react';
import { FlatTask, Category, DeadlineStatus } from '../types';
import { getDeadlineStatus, formatDeadlineBadge, getDeadlineBadgeClass } from '../utils/deadlineUtils';
import { formatDateShort } from '../utils/timeUtils';

interface DeadlineViewProps {
  tasks: FlatTask[];
  categories: Category[];
  onEdit: (task: FlatTask) => void;
  onStatusChange: (id: string, status: 'todo' | 'in_progress' | 'done') => void;
}

const GROUPS: { key: DeadlineStatus; label: string; emoji: string }[] = [
  { key: 'overdue', label: '期限切れ', emoji: '🔴' },
  { key: 'today', label: '今日まで', emoji: '🟠' },
  { key: 'tomorrow', label: '明日まで', emoji: '🟡' },
  { key: 'soon', label: '今週中', emoji: '🔵' },
  { key: 'ok', label: 'それ以降', emoji: '✅' },
];

const DeadlineView: React.FC<DeadlineViewProps> = ({ tasks, categories, onEdit, onStatusChange }) => {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const catMap = Object.fromEntries(categories.map(c => [c.id, c]));

  const withDeadline = tasks.filter(t => t.dueDate && t.status !== 'done');
  const grouped = GROUPS.map(g => ({
    ...g,
    tasks: withDeadline.filter(t => getDeadlineStatus(t.dueDate) === g.key),
  }));

  const toggleGroup = (key: string) => setCollapsed(c => ({ ...c, [key]: !c[key] }));

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      <div className="mb-4">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white">⚠️ 期限管理</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
          期限のあるタスクをステータス別に管理します
        </p>
      </div>

      <div className="space-y-4">
        {grouped.map(group => {
          if (group.tasks.length === 0 && group.key !== 'overdue') return null;
          const isCollapsed = collapsed[group.key];

          return (
            <div key={group.key} className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              <button
                onClick={() => toggleGroup(group.key)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
              >
                <span className="text-base">{group.emoji}</span>
                <span className="font-semibold text-gray-900 dark:text-white flex-1 text-left">
                  {group.label}
                </span>
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                  {group.tasks.length}件
                </span>
                {isCollapsed ? <ChevronRight size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
              </button>

              {!isCollapsed && (
                <div className="border-t border-gray-100 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700">
                  {group.tasks.length === 0 ? (
                    <div className="px-4 py-6 text-center text-sm text-gray-400 dark:text-gray-500">
                      該当するタスクはありません
                    </div>
                  ) : (
                    group.tasks.map(task => {
                      const cat = catMap[task.categoryId];
                      const status = getDeadlineStatus(task.dueDate);
                      const badge = formatDeadlineBadge(task.dueDate);
                      const badgeCls = getDeadlineBadgeClass(status);

                      return (
                        <div
                          key={task.id}
                          className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700/30 cursor-pointer transition-colors"
                          style={cat ? { borderLeft: `3px solid ${cat.color}` } : {}}
                          onClick={() => onEdit(task)}
                        >
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{task.title}</p>
                            <div className="flex items-center gap-2 mt-0.5">
                              {cat && <span className="text-xs text-gray-500 dark:text-gray-400">{cat.name}</span>}
                              {task.dueDate && (
                                <span className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                                  <Clock size={10} />
                                  {formatDateShort(task.dueDate)}
                                </span>
                              )}
                            </div>
                          </div>
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${badgeCls}`}>
                            {badge}
                          </span>
                          <select
                            value={task.status}
                            onChange={e => { e.stopPropagation(); onStatusChange(task.id, e.target.value as 'todo' | 'in_progress' | 'done'); }}
                            onClick={e => e.stopPropagation()}
                            className="text-xs bg-gray-100 dark:bg-gray-700 border-0 rounded-lg px-2 py-1 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          >
                            <option value="todo">未着手</option>
                            <option value="in_progress">進行中</option>
                            <option value="done">完了</option>
                          </select>
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {withDeadline.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
          <div className="text-4xl mb-4">🎉</div>
          <p className="text-base font-medium">期限切れのタスクはありません</p>
        </div>
      )}
    </div>
  );
};

export default DeadlineView;
