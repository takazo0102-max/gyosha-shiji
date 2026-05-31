import React from 'react';
import { FlatTask, Category } from '../types';
import { parseTimeToMinutes, formatMinutes } from '../utils/timeUtils';

interface TimelineProps {
  tasks: FlatTask[];
  categories: Category[];
  onStatusChange: (id: string, status: 'done') => void;
}

const HOUR_HEIGHT = 60; // px per hour
const START_HOUR = 6;
const END_HOUR = 24;

const Timeline: React.FC<TimelineProps> = ({ tasks, categories, onStatusChange }) => {
  const catMap = Object.fromEntries(categories.map(c => [c.id, c]));

  const scheduledTasks = tasks.filter(t => t.scheduledTime?.start && t.scheduledTime?.end);
  const unscheduledTasks = tasks.filter(t => !t.scheduledTime?.start);

  const totalMinutes = tasks.reduce((s, t) => s + (t.estimatedMinutes ?? 0), 0);

  const getTopOffset = (time: string) => {
    const mins = parseTimeToMinutes(time);
    return ((mins / 60) - START_HOUR) * HOUR_HEIGHT;
  };

  const getHeight = (start: string, end: string) => {
    const startMins = parseTimeToMinutes(start);
    const endMins = parseTimeToMinutes(end);
    const diff = Math.max(endMins - startMins, 30);
    return (diff / 60) * HOUR_HEIGHT;
  };

  const hours = Array.from({ length: END_HOUR - START_HOUR }, (_, i) => i + START_HOUR);
  const totalHeight = (END_HOUR - START_HOUR) * HOUR_HEIGHT;

  const now = new Date();
  const nowMins = now.getHours() * 60 + now.getMinutes();
  const nowTop = ((nowMins / 60) - START_HOUR) * HOUR_HEIGHT;
  const showNowLine = now.getHours() >= START_HOUR && now.getHours() < END_HOUR;

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      {/* Summary */}
      <div className="mb-4 flex items-center gap-4 flex-wrap">
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl px-4 py-2.5 flex items-center gap-2">
          <span className="text-sm text-blue-700 dark:text-blue-300 font-medium">
            今日の合計: {formatMinutes(totalMinutes)}
          </span>
        </div>
        <div className="text-sm text-gray-500 dark:text-gray-400">
          {tasks.length}件のタスク
        </div>
      </div>

      {/* Timeline */}
      {scheduledTasks.length > 0 && (
        <div className="mb-6">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">タイムライン</h3>
          <div className="relative bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="flex">
              {/* Hour labels */}
              <div className="w-14 flex-shrink-0 relative" style={{ height: totalHeight }}>
                {hours.map(h => (
                  <div
                    key={h}
                    className="absolute left-0 right-0 flex items-start justify-end pr-2"
                    style={{ top: (h - START_HOUR) * HOUR_HEIGHT - 8 }}
                  >
                    <span className="text-xs text-gray-400 dark:text-gray-500">{String(h).padStart(2, '0')}:00</span>
                  </div>
                ))}
              </div>

              {/* Grid + tasks */}
              <div className="flex-1 relative border-l border-gray-200 dark:border-gray-700" style={{ height: totalHeight }}>
                {/* Hour lines */}
                {hours.map(h => (
                  <div
                    key={h}
                    className="absolute left-0 right-0 border-t border-gray-100 dark:border-gray-700/50"
                    style={{ top: (h - START_HOUR) * HOUR_HEIGHT }}
                  />
                ))}

                {/* Now line */}
                {showNowLine && (
                  <div
                    className="absolute left-0 right-0 border-t-2 border-red-400 z-10"
                    style={{ top: nowTop }}
                  >
                    <div className="absolute -left-1 -top-1.5 w-3 h-3 rounded-full bg-red-400" />
                  </div>
                )}

                {/* Task blocks */}
                {scheduledTasks.map(task => {
                  const cat = catMap[task.categoryId];
                  const top = getTopOffset(task.scheduledTime!.start);
                  const height = getHeight(task.scheduledTime!.start, task.scheduledTime!.end);
                  const isDone = task.status === 'done';

                  return (
                    <div
                      key={task.id}
                      className={`absolute left-2 right-2 rounded-lg px-2.5 py-1.5 cursor-pointer transition-all hover:shadow-md ${
                        isDone ? 'opacity-50' : ''
                      }`}
                      style={{
                        top,
                        height: Math.max(height, 28),
                        backgroundColor: cat ? `${cat.color}25` : '#E5E7EB',
                        borderLeft: `3px solid ${cat?.color ?? '#9CA3AF'}`,
                      }}
                      onClick={() => !isDone && onStatusChange(task.id, 'done')}
                    >
                      <p className={`text-xs font-medium leading-tight ${isDone ? 'line-through' : ''}`}
                        style={{ color: cat?.color ?? '#374151' }}>
                        {task.title}
                      </p>
                      {height > 40 && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                          {task.scheduledTime!.start} 〜 {task.scheduledTime!.end}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Unscheduled */}
      {unscheduledTasks.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
            時刻未設定 ({unscheduledTasks.length}件)
          </h3>
          <div className="space-y-2">
            {unscheduledTasks.map(task => {
              const cat = catMap[task.categoryId];
              const isDone = task.status === 'done';
              return (
                <div
                  key={task.id}
                  className={`flex items-center gap-3 bg-white dark:bg-gray-800 rounded-xl p-3 border border-gray-200 dark:border-gray-700 cursor-pointer hover:shadow-sm transition-all ${
                    isDone ? 'opacity-50' : ''
                  }`}
                  style={{ borderLeft: `3px solid ${cat?.color ?? '#9CA3AF'}` }}
                  onClick={() => !isDone && onStatusChange(task.id, 'done')}
                >
                  <div className="flex-1">
                    <p className={`text-sm font-medium text-gray-900 dark:text-white ${isDone ? 'line-through' : ''}`}>
                      {task.title}
                    </p>
                    {task.estimatedMinutes && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        ⏱ {formatMinutes(task.estimatedMinutes)}
                      </p>
                    )}
                  </div>
                  {cat && (
                    <span className="text-xs px-2 py-1 rounded-full text-white" style={{ backgroundColor: cat.color }}>
                      {cat.name}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {tasks.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
          <div className="text-4xl mb-4">✅</div>
          <p className="text-base font-medium">今日のタスクはありません</p>
          <p className="text-sm mt-1">タスクに「今日やる」フラグを設定してください</p>
        </div>
      )}
    </div>
  );
};

export default Timeline;
