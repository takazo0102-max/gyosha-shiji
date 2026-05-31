import { useState, useCallback, useMemo } from 'react';
import { FlatTask, Task, TaskFormData } from '../types';
import { loadTasks, saveTasks } from '../utils/storage';

const generateId = () => `task-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

export const buildTree = (flatTasks: FlatTask[]): Task[] => {
  const map = new Map<string, Task>();
  const roots: Task[] = [];

  flatTasks.forEach(t => map.set(t.id, { ...t, children: [] }));

  flatTasks
    .slice()
    .sort((a, b) => a.order - b.order)
    .forEach(t => {
      const node = map.get(t.id)!;
      if (t.parentId && map.has(t.parentId)) {
        map.get(t.parentId)!.children.push(node);
      } else {
        roots.push(node);
      }
    });

  return roots.sort((a, b) => a.order - b.order);
};

export const flattenTree = (tasks: Task[]): FlatTask[] => {
  const result: FlatTask[] = [];
  const visit = (t: Task) => {
    const { children, ...flat } = t;
    result.push(flat);
    children.forEach(visit);
  };
  tasks.forEach(visit);
  return result;
};

export const calculateProgress = (task: Task): { completed: number; total: number } => {
  if (task.children.length === 0) return { completed: 0, total: 0 };
  const countAll = (t: Task): { completed: number; total: number } => {
    if (t.children.length === 0) return { completed: t.status === 'done' ? 1 : 0, total: 1 };
    const childResults = t.children.map(countAll);
    return {
      completed: childResults.reduce((s, r) => s + r.completed, 0),
      total: childResults.reduce((s, r) => s + r.total, 0),
    };
  };
  const childResults = task.children.map(countAll);
  return {
    completed: childResults.reduce((s, r) => s + r.completed, 0),
    total: childResults.reduce((s, r) => s + r.total, 0),
  };
};

export const useTasks = () => {
  const [flatTasks, setFlatTasks] = useState<FlatTask[]>(() => loadTasks());

  const tasks = useMemo(() => buildTree(flatTasks), [flatTasks]);

  const persist = useCallback((updated: FlatTask[]) => {
    setFlatTasks(updated);
    saveTasks(updated);
  }, []);

  const addTask = useCallback((data: TaskFormData): string => {
    const siblings = flatTasks.filter(t => t.parentId === data.parentId);
    const maxOrder = siblings.length ? Math.max(...siblings.map(t => t.order)) : -1;
    const newTask: FlatTask = {
      id: generateId(),
      title: data.title,
      description: data.description,
      categoryId: data.categoryId,
      priority: data.priority,
      status: data.status,
      dueDate: data.dueDate,
      isTodayTask: data.isTodayTask,
      scheduledTime: data.scheduledTime,
      estimatedMinutes: data.estimatedMinutes,
      parentId: data.parentId,
      order: maxOrder + 1,
      createdAt: new Date().toISOString(),
    };
    persist([...flatTasks, newTask]);
    return newTask.id;
  }, [flatTasks, persist]);

  const updateTask = useCallback((id: string, updates: Partial<Omit<FlatTask, 'id' | 'createdAt'>>) => {
    persist(flatTasks.map(t => t.id === id ? { ...t, ...updates } : t));
  }, [flatTasks, persist]);

  const deleteTask = useCallback((id: string) => {
    const toDelete = new Set<string>();
    const collectIds = (tid: string) => {
      toDelete.add(tid);
      flatTasks.filter(t => t.parentId === tid).forEach(c => collectIds(c.id));
    };
    collectIds(id);
    persist(flatTasks.filter(t => !toDelete.has(t.id)));
  }, [flatTasks, persist]);

  const moveTask = useCallback((id: string, newParentId: string | undefined, newOrder: number) => {
    persist(flatTasks.map(t => t.id === id ? { ...t, parentId: newParentId, order: newOrder } : t));
  }, [flatTasks, persist]);

  const reorderTasks = useCallback((parentId: string | undefined, orderedIds: string[]) => {
    const updates = new Map(orderedIds.map((id, i) => [id, i]));
    persist(flatTasks.map(t => updates.has(t.id) ? { ...t, order: updates.get(t.id)! } : t));
  }, [flatTasks, persist]);

  const getTaskById = useCallback((id: string): FlatTask | undefined => {
    return flatTasks.find(t => t.id === id);
  }, [flatTasks]);

  const todayTasks = useMemo(() =>
    flatTasks.filter(t => t.isTodayTask && t.status !== 'done'),
    [flatTasks]
  );

  return {
    flatTasks,
    tasks,
    addTask,
    updateTask,
    deleteTask,
    moveTask,
    reorderTasks,
    getTaskById,
    todayTasks,
  };
};
