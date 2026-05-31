import React, { useState } from 'react';
import {
  ChevronRight, ChevronDown, Plus, Edit2, Trash2,
  Check, Clock, Flag, Circle, CheckCircle2, PlayCircle,
} from 'lucide-react';
import { Task, Category, FlatTask } from '../types';
import { getDeadlineStatus } from '../utils/deadlineUtils';
import { getDeadlineBgClass } from '../utils/deadlineUtils';
import { formatDateShort } from '../utils/timeUtils';
import { calculateProgress } from '../hooks/useTasks';
import DeadlineBadge from './DeadlineBadge';

interface TaskNodeProps {
  task: Task;
  categories: Category[];
  depth: number;
  onEdit: (task: FlatTask) => void;
  onDelete: (id: string) => void;
  onAddChild: (parentId: string) => void;
  onStatusChange: (id: string, status: 'todo' | 'in_progress' | 'done') => void;
  onTodayToggle: (id: string, value: boolean) => void;
}

const PRIORITY_ICON_COLOR: Record<string, string> = {
  high: 'text-red-500', medium: 'text-yellow-500', low: 'text-green-500',
};

const TaskNode: React.FC<TaskNodeProps> = ({
  task, categories, depth, onEdit, onDelete, onAddChild, onStatusChange, onTodayToggle,
}) => {
  const [collapsed, setCollapsed] = useState(false);
  const cat = categories.find(c => c.id === task.categoryId);
  const deadlineStatus = getDeadlineStatus(task.dueDate);
  const progress = calculateProgress(task);
  const isDone = task.status === 'done';

  const nextStatus = () => {
    const cycle: Record<string, 'todo' | 'in_progress' | 'done'> = {
      todo: 'in_progress', in_progress: 'done', done: 'todo',
    };
    onStatusChange(task.id, cycle[task.status]);
  };

  const StatusIcon = task.status === 'done' ? CheckCircle2
    : task.status === 'in_progress' ? PlayCircle
    : Circle;
  const statusColor = task.status === 'done' ? 'text-green-500'
    : task.status === 'in_progress' ? 'text-blue-500'
    : 'text-gray-400 dark:text-gray-500';

  const hasChildren = task.children.length > 0;
  const deadlineBg = !isDone ? getDeadlineBgClass(deadlineStatus) : '';

  return (
    <div className="animate-fade-in">
      <div
        className={`group relative flex items-start gap-2 px-3 py-2.5 rounded-xl mb-1 transition-all hover:bg-gray-50 dark:hover:bg-gray-800/60 ${
          isDone ? 'opacity-50' : ''
        } ${deadlineBg || 'bg-white dark:bg-gray-800/40 border border-gray-100 dark:border-gray-700/50'}`}
        style={{ marginLeft: `${depth * 20}px` }}
      >
        {/* Category color bar */}
        {cat && (
          <div
            className="absolute left-0 top-0 bottom-0 w-1 rounded-l-xl"
            style={{ backgroundColor: cat.color }}
          />
        )}

        {/* Collapse toggle */}
        <button
          onClick={() => hasChildren && setCollapsed(c => !c)}
          className={`flex-shrink-0 mt-0.5 transition-colors ${
            hasChildren ? 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300' : 'text-transparent'
          }`}
        >
          {hasChildren
            ? collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />
            : <span className="inline-block w-4 h-4" />
          }
        </button>

        {/* Status icon */}
        <button
          onClick={nextStatus}
          className={`flex-shrink-0 mt-0.5 transition-colors hover:scale-110 ${statusColor}`}
          title="ステータスを変更"
        >
          <StatusIcon size={18} />
        </button>

        {/* Content */}
        <div className="flex-1 min-w-0 pl-1">
          <div className="flex items-start gap-2 flex-wrap">
            <span className={`text-sm font-medium text-gray-900 dark:text-white ${isDone ? 'line-through' : ''} flex-1`}>
              {task.title}
            </span>

            {/* Priority */}
            <Flag size={12} className={`flex-shrink-0 mt-0.5 ${PRIORITY_ICON_COLOR[task.priority]}`} />

            {/* Deadline badge */}
            {task.dueDate && !isDone && (
              <DeadlineBadge dueDate={task.dueDate} status={deadlineStatus} />
            )}

            {/* Today badge */}
            {task.isTodayTask && !isDone && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300">
                今日
              </span>
            )}
          </div>

          {/* Description */}
          {task.description && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">{task.description}</p>
          )}

          {/* Meta row */}
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            {cat && (
              <span className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: cat.color }} />
                {cat.name}
              </span>
            )}
            {task.dueDate && (
              <span className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
                <Clock size={10} />
                {formatDateShort(task.dueDate)}
              </span>
            )}
            {task.estimatedMinutes && (
              <span className="text-xs text-gray-400 dark:text-gray-500">
                ⏱ {task.estimatedMinutes}分
              </span>
            )}
          </div>

          {/* Progress bar */}
          {progress.total > 0 && (
            <div className="mt-2 flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all duration-300"
                  style={{ width: `${(progress.completed / progress.total) * 100}%` }}
                />
              </div>
              <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
                {progress.completed}/{progress.total}
              </span>
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex-shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => onTodayToggle(task.id, !task.isTodayTask)}
            className={`p-1 rounded transition-colors ${
              task.isTodayTask
                ? 'text-purple-500 bg-purple-100 dark:bg-purple-900/30'
                : 'text-gray-400 hover:text-purple-500 hover:bg-purple-50 dark:hover:bg-purple-900/20'
            }`}
            title="今日やるに追加/削除"
          >
            <Check size={13} />
          </button>
          <button
            onClick={() => onAddChild(task.id)}
            className="p-1 rounded text-gray-400 hover:text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors"
            title="サブタスクを追加"
          >
            <Plus size={13} />
          </button>
          <button
            onClick={() => onEdit(task)}
            className="p-1 rounded text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
            title="編集"
          >
            <Edit2 size={13} />
          </button>
          <button
            onClick={() => onDelete(task.id)}
            className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
            title="削除"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {/* Children */}
      {hasChildren && !collapsed && (
        <div>
          {task.children.map(child => (
            <TaskNode
              key={child.id}
              task={child}
              categories={categories}
              depth={depth + 1}
              onEdit={onEdit}
              onDelete={onDelete}
              onAddChild={onAddChild}
              onStatusChange={onStatusChange}
              onTodayToggle={onTodayToggle}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default TaskNode;
