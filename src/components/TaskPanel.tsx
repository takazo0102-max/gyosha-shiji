import React, { useState, useEffect } from 'react';
import { X, Calendar, Clock, Flag, Tag, AlignLeft, Plus } from 'lucide-react';
import { FlatTask, Category, TaskFormData, Priority, Status } from '../types';

interface TaskPanelProps {
  task?: FlatTask;
  parentTask?: FlatTask;
  categories: Category[];
  onSave: (data: TaskFormData) => void;
  onClose: () => void;
}

const PRIORITY_LABELS: Record<Priority, string> = { high: '高', medium: '中', low: '低' };
const PRIORITY_COLORS: Record<Priority, string> = {
  high: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  medium: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
  low: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
};
const STATUS_LABELS: Record<Status, string> = { todo: '未着手', in_progress: '進行中', done: '完了' };

const TaskPanel: React.FC<TaskPanelProps> = ({ task, parentTask, categories, onSave, onClose }) => {
  const defaultCategory = categories[0]?.id ?? '';
  const [form, setForm] = useState<TaskFormData>({
    title: task?.title ?? '',
    description: task?.description ?? '',
    categoryId: task?.categoryId ?? defaultCategory,
    priority: task?.priority ?? 'medium',
    status: task?.status ?? 'todo',
    dueDate: task?.dueDate ?? '',
    isTodayTask: task?.isTodayTask ?? false,
    scheduledTime: task?.scheduledTime,
    estimatedMinutes: task?.estimatedMinutes,
    parentId: task?.parentId ?? parentTask?.id,
  });

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const set = <K extends keyof TaskFormData>(key: K, value: TaskFormData[K]) =>
    setForm(prev => ({ ...prev, [key]: value }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) return;
    onSave({ ...form, title: form.title.trim(), dueDate: form.dueDate || undefined });
  };

  const inputCls = "w-full bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all";
  const labelCls = "text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5 flex items-center gap-1.5";

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="absolute inset-0 bg-black/30 dark:bg-black/50" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white dark:bg-gray-900 shadow-2xl flex flex-col animate-slide-in h-full">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
              {task ? 'タスクを編集' : 'タスクを追加'}
            </h2>
            {parentTask && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                親: {parentTask.title}
              </p>
            )}
          </div>
          <button onClick={onClose} className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* Title */}
          <div>
            <label className={labelCls}>タイトル *</label>
            <input
              autoFocus
              value={form.title}
              onChange={e => set('title', e.target.value)}
              placeholder="タスクのタイトルを入力..."
              className={inputCls}
              required
            />
          </div>

          {/* Description */}
          <div>
            <label className={labelCls}><AlignLeft size={12} />説明</label>
            <textarea
              value={form.description ?? ''}
              onChange={e => set('description', e.target.value)}
              placeholder="詳細な説明（任意）"
              rows={3}
              className={`${inputCls} resize-none`}
            />
          </div>

          {/* Category */}
          <div>
            <label className={labelCls}><Tag size={12} />カテゴリ</label>
            <div className="grid grid-cols-2 gap-2">
              {categories.map(cat => (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => set('categoryId', cat.id)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium transition-all ${
                    form.categoryId === cat.id
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                      : 'border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:border-gray-300 dark:hover:border-gray-500'
                  }`}
                >
                  <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: cat.color }} />
                  <span className="truncate">{cat.name}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Priority & Status */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}><Flag size={12} />優先度</label>
              <div className="space-y-1">
                {(['high', 'medium', 'low'] as Priority[]).map(p => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => set('priority', p)}
                    className={`w-full flex items-center justify-between px-3 py-1.5 rounded-lg border text-sm transition-all ${
                      form.priority === p
                        ? 'border-blue-500 ' + PRIORITY_COLORS[p]
                        : 'border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                    }`}
                  >
                    <span>{PRIORITY_LABELS[p]}</span>
                    {form.priority === p && <span className="w-1.5 h-1.5 rounded-full bg-current" />}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className={labelCls}>ステータス</label>
              <div className="space-y-1">
                {(['todo', 'in_progress', 'done'] as Status[]).map(s => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => set('status', s)}
                    className={`w-full flex items-center justify-between px-3 py-1.5 rounded-lg border text-sm transition-all ${
                      form.status === s
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                        : 'border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                    }`}
                  >
                    <span>{STATUS_LABELS[s]}</span>
                    {form.status === s && <span className="w-1.5 h-1.5 rounded-full bg-current" />}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Due Date & Estimated */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}><Calendar size={12} />期限日</label>
              <input
                type="date"
                value={form.dueDate ?? ''}
                onChange={e => set('dueDate', e.target.value)}
                className={inputCls}
              />
            </div>
            <div>
              <label className={labelCls}><Clock size={12} />見積（分）</label>
              <input
                type="number"
                min={0}
                step={5}
                value={form.estimatedMinutes ?? ''}
                onChange={e => set('estimatedMinutes', e.target.value ? Number(e.target.value) : undefined)}
                placeholder="60"
                className={inputCls}
              />
            </div>
          </div>

          {/* Today Task */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-4 space-y-3">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={form.isTodayTask}
                onChange={e => set('isTodayTask', e.target.checked)}
                className="w-4 h-4 rounded accent-blue-600"
              />
              <span className="text-sm font-medium text-gray-800 dark:text-gray-200">今日やるタスクに追加</span>
            </label>

            {form.isTodayTask && (
              <div className="space-y-2 animate-fade-in">
                <label className={labelCls}><Clock size={12} />予定時刻（任意）</label>
                <div className="flex items-center gap-2">
                  <input
                    type="time"
                    value={form.scheduledTime?.start ?? ''}
                    onChange={e => set('scheduledTime', { start: e.target.value, end: form.scheduledTime?.end ?? '' })}
                    className={`${inputCls} flex-1`}
                  />
                  <span className="text-gray-400 text-sm">〜</span>
                  <input
                    type="time"
                    value={form.scheduledTime?.end ?? ''}
                    onChange={e => set('scheduledTime', { start: form.scheduledTime?.start ?? '', end: e.target.value })}
                    className={`${inputCls} flex-1`}
                  />
                </div>
              </div>
            )}
          </div>
        </form>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            キャンセル
          </button>
          <button
            onClick={handleSubmit}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            {task ? '更新する' : '追加する'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default TaskPanel;
