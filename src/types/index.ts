export type Priority = 'high' | 'medium' | 'low';
export type Status = 'todo' | 'in_progress' | 'done';
export type DeadlineStatus = 'overdue' | 'today' | 'tomorrow' | 'soon' | 'ok';
export type View = 'tasks' | 'today' | 'deadline' | 'calendar' | 'categories';

export interface Category {
  id: string;
  name: string;
  color: string;
}

export interface ScheduledTime {
  start: string;
  end: string;
}

export interface FlatTask {
  id: string;
  title: string;
  description?: string;
  categoryId: string;
  priority: Priority;
  status: Status;
  dueDate?: string;
  isTodayTask: boolean;
  scheduledTime?: ScheduledTime;
  estimatedMinutes?: number;
  parentId?: string;
  order: number;
  createdAt: string;
}

export interface Task extends FlatTask {
  children: Task[];
}

export interface AlertSettings {
  warningDays: number;
  showBanner: boolean;
  browserNotifications: boolean;
}

export interface TaskFormData {
  title: string;
  description?: string;
  categoryId: string;
  priority: Priority;
  status: Status;
  dueDate?: string;
  isTodayTask: boolean;
  scheduledTime?: ScheduledTime;
  estimatedMinutes?: number;
  parentId?: string;
}
