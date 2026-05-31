import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { FlatTask, Category } from '../types';
import { getCalendarDays, dateToString, getTodayString } from '../utils/timeUtils';
import { getDeadlineStatus } from '../utils/deadlineUtils';

interface CalendarViewProps {
  tasks: FlatTask[];
  categories: Category[];
  onEdit: (task: FlatTask) => void;
}

const CalendarView: React.FC<CalendarViewProps> = ({ tasks, categories, onEdit }) => {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const catMap = Object.fromEntries(categories.map(c => [c.id, c]));
  const todayStr = getTodayString();

  const days = getCalendarDays(year, month);

  const tasksByDate = tasks.reduce<Record<string, FlatTask[]>>((acc, t) => {
    if (t.dueDate) {
      if (!acc[t.dueDate]) acc[t.dueDate] = [];
      acc[t.dueDate].push(t);
    }
    return acc;
  }, {});

  const prevMonth = () => {
    if (month === 0) { setYear(y => y - 1); setMonth(11); }
    else setMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (month === 11) { setYear(y => y + 1); setMonth(0); }
    else setMonth(m => m + 1);
  };

  const selectedTasks = selectedDate ? (tasksByDate[selectedDate] ?? []) : [];

  const DOW_LABELS = ['日', '月', '火', '水', '木', '金', '土'];

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white">📅 カレンダー</h2>
        <div className="flex-1" />
        <button onClick={prevMonth} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
          <ChevronLeft size={18} className="text-gray-600 dark:text-gray-400" />
        </button>
        <span className="text-base font-semibold text-gray-800 dark:text-gray-200 min-w-32 text-center">
          {year}年{month + 1}月
        </span>
        <button onClick={nextMonth} className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
          <ChevronRight size={18} className="text-gray-600 dark:text-gray-400" />
        </button>
        <button
          onClick={() => { setYear(now.getFullYear()); setMonth(now.getMonth()); }}
          className="text-sm px-3 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-lg hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
        >
          今月
        </button>
      </div>

      {/* Calendar Grid */}
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden mb-4">
        {/* Day of week headers */}
        <div className="grid grid-cols-7 border-b border-gray-200 dark:border-gray-700">
          {DOW_LABELS.map((d, i) => (
            <div
              key={d}
              className={`py-2.5 text-center text-xs font-semibold ${
                i === 0 ? 'text-red-500' : i === 6 ? 'text-blue-500' : 'text-gray-500 dark:text-gray-400'
              }`}
            >
              {d}
            </div>
          ))}
        </div>

        {/* Days */}
        <div className="grid grid-cols-7">
          {days.map(({ date, currentMonth }, idx) => {
            const dateStr = dateToString(date);
            const dayTasks = tasksByDate[dateStr] ?? [];
            const isToday = dateStr === todayStr;
            const isSelected = dateStr === selectedDate;
            const isOverdue = currentMonth && date < new Date(todayStr + 'T00:00:00');
            const dow = date.getDay();

            return (
              <div
                key={idx}
                onClick={() => dayTasks.length > 0 && setSelectedDate(dateStr === selectedDate ? null : dateStr)}
                className={`min-h-16 p-1.5 border-b border-r border-gray-100 dark:border-gray-700/50 transition-colors ${
                  currentMonth ? '' : 'bg-gray-50 dark:bg-gray-800/50'
                } ${dayTasks.length > 0 ? 'cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20' : ''} ${
                  isSelected ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                } ${isOverdue && dayTasks.some(t => t.status !== 'done') ? 'bg-red-50 dark:bg-red-900/10' : ''}`}
              >
                <div className={`text-xs font-medium mb-1 w-6 h-6 flex items-center justify-center rounded-full ${
                  isToday ? 'bg-blue-600 text-white' :
                  !currentMonth ? 'text-gray-300 dark:text-gray-600' :
                  dow === 0 ? 'text-red-500' : dow === 6 ? 'text-blue-500' : 'text-gray-700 dark:text-gray-300'
                }`}>
                  {date.getDate()}
                </div>

                {/* Task dots */}
                {dayTasks.length > 0 && (
                  <div className="flex flex-wrap gap-0.5 mt-0.5">
                    {dayTasks.slice(0, 4).map(task => {
                      const cat = catMap[task.categoryId];
                      return (
                        <div
                          key={task.id}
                          className="w-2 h-2 rounded-full opacity-80"
                          style={{ backgroundColor: cat?.color ?? '#9CA3AF' }}
                          title={task.title}
                        />
                      );
                    })}
                    {dayTasks.length > 4 && (
                      <span className="text-gray-400 dark:text-gray-500 text-xs">+{dayTasks.length - 4}</span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Selected date popup */}
      {selectedDate && selectedTasks.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden animate-fade-in">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-700">
            <h3 className="font-semibold text-gray-900 dark:text-white">
              {new Date(selectedDate + 'T00:00:00').toLocaleDateString('ja-JP', { month: 'long', day: 'numeric', weekday: 'short' })}
              <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
                {selectedTasks.length}件のタスク
              </span>
            </h3>
            <button
              onClick={() => setSelectedDate(null)}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <X size={16} />
            </button>
          </div>
          <div className="divide-y divide-gray-100 dark:divide-gray-700">
            {selectedTasks.map(task => {
              const cat = catMap[task.categoryId];
              const status = getDeadlineStatus(task.dueDate);
              return (
                <button
                  key={task.id}
                  onClick={() => onEdit(task)}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700/40 text-left transition-colors"
                  style={cat ? { borderLeft: `3px solid ${cat.color}` } : {}}
                >
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium text-gray-900 dark:text-white ${task.status === 'done' ? 'line-through opacity-50' : ''}`}>
                      {task.title}
                    </p>
                    {cat && <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{cat.name}</p>}
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    task.status === 'done' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' :
                    status === 'overdue' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' :
                    'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                  }`}>
                    {task.status === 'done' ? '完了' : task.status === 'in_progress' ? '進行中' : '未着手'}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default CalendarView;
