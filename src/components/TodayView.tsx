import React from 'react';
import { FlatTask, Category } from '../types';
import Timeline from './Timeline';

interface TodayViewProps {
  todayTasks: FlatTask[];
  allTasks: FlatTask[];
  categories: Category[];
  onStatusChange: (id: string, status: 'done') => void;
  onAddTask: () => void;
}

const TodayView: React.FC<TodayViewProps> = ({ todayTasks, allTasks, categories, onStatusChange, onAddTask }) => {
  const now = new Date();
  const dateStr = now.toLocaleDateString('ja-JP', {
    year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
  });

  const completedToday = allTasks.filter(t => t.isTodayTask && t.status === 'done').length;
  const totalToday = allTasks.filter(t => t.isTodayTask).length;

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-4 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white">Today</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{dateStr}</p>
          </div>
          <button
            onClick={onAddTask}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
          >
            + タスク追加
          </button>
        </div>

        {totalToday > 0 && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
              <span>完了率</span>
              <span>{completedToday}/{totalToday}</span>
            </div>
            <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-blue-500 to-green-500 rounded-full transition-all duration-500"
                style={{ width: `${totalToday ? (completedToday / totalToday) * 100 : 0}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Timeline */}
      <Timeline
        tasks={todayTasks}
        categories={categories}
        onStatusChange={onStatusChange}
      />
    </div>
  );
};

export default TodayView;
