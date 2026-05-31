import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Menu, Bell } from 'lucide-react';
import { View, FlatTask, TaskFormData } from './types';
import { useTasks } from './hooks/useTasks';
import { useCategories } from './hooks/useCategories';
import { loadSettings, saveSettings } from './utils/storage';
import { getDeadlineStatus } from './utils/deadlineUtils';
import Sidebar from './components/Sidebar';
import AlertBanner from './components/AlertBanner';
import TaskTree from './components/TaskTree';
import TaskPanel from './components/TaskPanel';
import TodayView from './components/TodayView';
import DeadlineView from './components/DeadlineView';
import CalendarView from './components/CalendarView';
import CategoryManager from './components/CategoryManager';

const App: React.FC = () => {
  const [view, setView] = useState<View>('tasks');
  const [darkMode, setDarkMode] = useState(() => {
    const stored = localStorage.getItem('taskflow_dark');
    return stored ? stored === 'true' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<FlatTask | undefined>();
  const [parentTaskId, setParentTaskId] = useState<string | undefined>();
  const [categoryFilter, setCategoryFilter] = useState('');

  const { flatTasks, tasks, addTask, updateTask, deleteTask, getTaskById, todayTasks } = useTasks();
  const { categories, addCategory, updateCategory, deleteCategory, getCategoryById } = useCategories();

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
    localStorage.setItem('taskflow_dark', String(darkMode));
  }, [darkMode]);

  // Browser notification on load
  useEffect(() => {
    const settings = loadSettings();
    if (settings.browserNotifications && 'Notification' in window && Notification.permission === 'granted') {
      const urgentTasks = flatTasks.filter(t => {
        const s = getDeadlineStatus(t.dueDate);
        return t.status !== 'done' && (s === 'overdue' || s === 'today');
      });
      if (urgentTasks.length > 0) {
        const overdue = urgentTasks.filter(t => getDeadlineStatus(t.dueDate) === 'overdue').length;
        const todayDue = urgentTasks.filter(t => getDeadlineStatus(t.dueDate) === 'today').length;
        const parts = [];
        if (overdue) parts.push(`🔴 期限切れ ${overdue}件`);
        if (todayDue) parts.push(`🟠 今日期限 ${todayDue}件`);
        new Notification('TaskFlow - 期限アラート', { body: parts.join('\n') });
      }
    }
  }, []);

  const openAddPanel = useCallback((parentId?: string) => {
    setEditingTask(undefined);
    setParentTaskId(parentId);
    setPanelOpen(true);
  }, []);

  const openEditPanel = useCallback((task: FlatTask) => {
    setEditingTask(task);
    setParentTaskId(undefined);
    setPanelOpen(true);
  }, []);

  const closePanel = useCallback(() => {
    setPanelOpen(false);
    setEditingTask(undefined);
    setParentTaskId(undefined);
  }, []);

  const handleSave = useCallback((data: TaskFormData) => {
    if (editingTask) {
      updateTask(editingTask.id, data);
    } else {
      addTask(data);
    }
    closePanel();
  }, [editingTask, updateTask, addTask, closePanel]);

  const handleStatusChange = useCallback((id: string, status: 'todo' | 'in_progress' | 'done') => {
    updateTask(id, { status });
  }, [updateTask]);

  const handleTodayToggle = useCallback((id: string, value: boolean) => {
    updateTask(id, { isTodayTask: value });
  }, [updateTask]);

  const handleTodayStatusChange = useCallback((id: string, status: 'done') => {
    updateTask(id, { status });
  }, [updateTask]);

  const taskCountByCategory = useMemo(() =>
    Object.fromEntries(categories.map(c => [c.id, flatTasks.filter(t => t.categoryId === c.id).length])),
    [categories, flatTasks]
  );

  const filteredTasks = useMemo(() => {
    if (!categoryFilter) return tasks;
    const filterTree = (taskList: typeof tasks): typeof tasks =>
      taskList
        .map(t => ({ ...t, children: filterTree(t.children) }))
        .filter(t => t.categoryId === categoryFilter || t.children.length > 0);
    return filterTree(tasks);
  }, [tasks, categoryFilter]);

  const parentTask = parentTaskId ? getTaskById(parentTaskId) : undefined;

  return (
    <div className="flex h-screen bg-gray-100 dark:bg-gray-900 overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        view={view}
        onViewChange={setView}
        categories={categories}
        tasks={flatTasks}
        darkMode={darkMode}
        onToggleDark={() => setDarkMode(d => !d)}
        mobileOpen={mobileMenuOpen}
        onMobileClose={() => setMobileMenuOpen(false)}
        onCategoryFilter={setCategoryFilter}
        activeCategoryFilter={categoryFilter}
      />

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* Top bar (mobile) */}
        <div className="lg:hidden flex items-center gap-3 px-4 py-3 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setMobileMenuOpen(true)}
            className="p-2 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <Menu size={20} />
          </button>
          <span className="font-bold text-gray-900 dark:text-white flex-1">TaskFlow</span>
          <button
            onClick={() => {
              if ('Notification' in window) {
                Notification.requestPermission().then(p => {
                  if (p === 'granted') {
                    const s = loadSettings();
                    saveSettings({ ...s, browserNotifications: true });
                  }
                });
              }
            }}
            className="p-2 rounded-lg text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <Bell size={20} />
          </button>
        </div>

        {/* Alert Banner */}
        <AlertBanner
          tasks={flatTasks}
          categories={categories}
          onTaskClick={id => {
            const t = flatTasks.find(t => t.id === id);
            if (t) openEditPanel(t);
          }}
        />

        {/* View content */}
        <div className="flex-1 overflow-hidden">
          {view === 'tasks' && (
            <TaskTree
              tasks={filteredTasks}
              flatTasks={flatTasks}
              categories={categories}
              onEdit={openEditPanel}
              onDelete={deleteTask}
              onAddTask={openAddPanel}
              onStatusChange={handleStatusChange}
              onTodayToggle={handleTodayToggle}
            />
          )}

          {view === 'today' && (
            <TodayView
              todayTasks={todayTasks}
              allTasks={flatTasks}
              categories={categories}
              onStatusChange={handleTodayStatusChange}
              onAddTask={() => openAddPanel()}
            />
          )}

          {view === 'deadline' && (
            <DeadlineView
              tasks={flatTasks}
              categories={categories}
              onEdit={openEditPanel}
              onStatusChange={handleStatusChange}
            />
          )}

          {view === 'calendar' && (
            <CalendarView
              tasks={flatTasks}
              categories={categories}
              onEdit={openEditPanel}
            />
          )}

          {view === 'categories' && (
            <CategoryManager
              categories={categories}
              onAdd={addCategory}
              onUpdate={updateCategory}
              onDelete={deleteCategory}
              taskCountByCategory={taskCountByCategory}
            />
          )}
        </div>
      </div>

      {/* Task panel */}
      {panelOpen && (
        <TaskPanel
          task={editingTask}
          parentTask={parentTask}
          categories={categories}
          onSave={handleSave}
          onClose={closePanel}
        />
      )}
    </div>
  );
};

export default App;
