import React, { useState, useMemo } from 'react';
import { Plus, Search, Filter, ChevronDown } from 'lucide-react';
import { Task, FlatTask, Category, Priority, Status } from '../types';
import TaskNode from './TaskNode';

interface TaskTreeProps {
  tasks: Task[];
  flatTasks: FlatTask[];
  categories: Category[];
  onEdit: (task: FlatTask) => void;
  onDelete: (id: string) => void;
  onAddTask: (parentId?: string) => void;
  onStatusChange: (id: string, status: Status) => void;
  onTodayToggle: (id: string, value: boolean) => void;
}

const TaskTree: React.FC<TaskTreeProps> = ({
  tasks, flatTasks, categories, onEdit, onDelete, onAddTask, onStatusChange, onTodayToggle,
}) => {
  const [search, setSearch] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterPriority, setFilterPriority] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [groupBy, setGroupBy] = useState<'category' | 'none'>('category');

  const selectCls = "bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 text-xs text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500";

  const filterTask = (t: FlatTask): boolean => {
    if (search && !t.title.toLowerCase().includes(search.toLowerCase()) && !(t.description?.toLowerCase().includes(search.toLowerCase()))) return false;
    if (filterCategory && t.categoryId !== filterCategory) return false;
    if (filterStatus && t.status !== filterStatus) return false;
    if (filterPriority && t.priority !== filterPriority) return false;
    return true;
  };

  const filteredIds = useMemo(() => {
    if (!search && !filterCategory && !filterStatus && !filterPriority) return null;
    return new Set(flatTasks.filter(filterTask).map(t => t.id));
  }, [search, filterCategory, filterStatus, filterPriority, flatTasks]);

  const filterTree = (taskList: Task[]): Task[] => {
    if (!filteredIds) return taskList;
    return taskList
      .map(t => ({ ...t, children: filterTree(t.children) }))
      .filter(t => filteredIds.has(t.id) || t.children.length > 0);
  };

  const filteredTasks = filterTree(tasks);

  const grouped = useMemo(() => {
    if (groupBy === 'none') return [{ cat: undefined, tasks: filteredTasks }];
    const map = new Map<string, Task[]>();
    const addToGroup = (taskList: Task[]) => {
      taskList.forEach(t => {
        const key = t.categoryId;
        if (!map.has(key)) map.set(key, []);
        map.get(key)!.push(t);
      });
    };
    addToGroup(filteredTasks);
    return categories.map(cat => ({ cat, tasks: map.get(cat.id) ?? [] }))
      .filter(g => g.tasks.length > 0);
  }, [filteredTasks, categories, groupBy]);

  const hasFilters = !!(search || filterCategory || filterStatus || filterPriority);

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Toolbar */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 space-y-2">
        <div className="flex items-center gap-2">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="タスクを検索..."
              className="w-full pl-9 pr-3 py-2 bg-gray-100 dark:bg-gray-800 border border-transparent rounded-xl text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white dark:focus:bg-gray-700 transition-all"
            />
          </div>
          <button
            onClick={() => setShowFilters(s => !s)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-medium transition-colors ${
              hasFilters || showFilters
                ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
          >
            <Filter size={14} />
            フィルター
            {hasFilters && <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />}
          </button>
          <button
            onClick={() => onAddTask()}
            className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-medium transition-colors"
          >
            <Plus size={14} />
            追加
          </button>
        </div>

        {showFilters && (
          <div className="flex items-center gap-2 flex-wrap animate-fade-in">
            <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)} className={selectCls}>
              <option value="">全カテゴリ</option>
              {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} className={selectCls}>
              <option value="">全ステータス</option>
              <option value="todo">未着手</option>
              <option value="in_progress">進行中</option>
              <option value="done">完了</option>
            </select>
            <select value={filterPriority} onChange={e => setFilterPriority(e.target.value)} className={selectCls}>
              <option value="">全優先度</option>
              <option value="high">高</option>
              <option value="medium">中</option>
              <option value="low">低</option>
            </select>
            <select value={groupBy} onChange={e => setGroupBy(e.target.value as 'category' | 'none')} className={selectCls}>
              <option value="category">カテゴリ別</option>
              <option value="none">グループなし</option>
            </select>
            {hasFilters && (
              <button
                onClick={() => { setSearch(''); setFilterCategory(''); setFilterStatus(''); setFilterPriority(''); }}
                className="text-xs text-red-500 hover:text-red-700 dark:text-red-400 px-2 py-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                クリア
              </button>
            )}
          </div>
        )}
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
        {grouped.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500">
            <div className="w-16 h-16 rounded-2xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center mb-4">
              <Search size={28} />
            </div>
            <p className="text-base font-medium">{hasFilters ? '条件に一致するタスクがありません' : 'タスクがありません'}</p>
            <p className="text-sm mt-1">{hasFilters ? 'フィルターを変更してください' : '「追加」ボタンで新しいタスクを作成してください'}</p>
          </div>
        ) : (
          grouped.map(({ cat, tasks: groupTasks }) => (
            <CategoryGroup
              key={cat?.id ?? 'all'}
              cat={cat}
              tasks={groupTasks}
              categories={categories}
              onEdit={onEdit}
              onDelete={onDelete}
              onAddTask={onAddTask}
              onStatusChange={onStatusChange}
              onTodayToggle={onTodayToggle}
            />
          ))
        )}
      </div>
    </div>
  );
};

interface CategoryGroupProps {
  cat?: Category;
  tasks: Task[];
  categories: Category[];
  onEdit: (task: FlatTask) => void;
  onDelete: (id: string) => void;
  onAddTask: (parentId?: string) => void;
  onStatusChange: (id: string, status: Status) => void;
  onTodayToggle: (id: string, value: boolean) => void;
}

const CategoryGroup: React.FC<CategoryGroupProps> = ({ cat, tasks, categories, onEdit, onDelete, onAddTask, onStatusChange, onTodayToggle }) => {
  const [collapsed, setCollapsed] = useState(false);
  const doneCount = tasks.filter(t => t.status === 'done').length;

  return (
    <div>
      {cat && (
        <div className="flex items-center gap-2 mb-3">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: cat.color }} />
          <button
            onClick={() => setCollapsed(c => !c)}
            className="flex items-center gap-1.5 text-sm font-semibold text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
          >
            {cat.name}
            <ChevronDown
              size={14}
              className={`text-gray-400 transition-transform duration-200 ${collapsed ? '-rotate-90' : ''}`}
            />
          </button>
          <span className="text-xs text-gray-400 dark:text-gray-500">
            {doneCount}/{tasks.length}
          </span>
          <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
          <button
            onClick={() => onAddTask()}
            className="text-xs text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
          >
            + 追加
          </button>
        </div>
      )}

      {!collapsed && (
        <div>
          {tasks.map(task => (
            <TaskNode
              key={task.id}
              task={task}
              categories={categories}
              depth={0}
              onEdit={onEdit}
              onDelete={onDelete}
              onAddChild={onAddTask}
              onStatusChange={onStatusChange}
              onTodayToggle={onTodayToggle}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default TaskTree;
