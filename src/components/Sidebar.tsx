import React from 'react';
import {
  LayoutDashboard, Sun, AlertTriangle, Calendar, Tags,
  Settings, X, Moon, ChevronRight,
} from 'lucide-react';
import { View, Category, FlatTask } from '../types';
import { getDeadlineStatus } from '../utils/deadlineUtils';

interface SidebarProps {
  view: View;
  onViewChange: (v: View) => void;
  categories: Category[];
  tasks: FlatTask[];
  darkMode: boolean;
  onToggleDark: () => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
  onCategoryFilter: (id: string) => void;
  activeCategoryFilter: string;
}

const Sidebar: React.FC<SidebarProps> = ({
  view, onViewChange, categories, tasks, darkMode, onToggleDark,
  mobileOpen, onMobileClose, onCategoryFilter, activeCategoryFilter,
}) => {
  const todayCount = tasks.filter(t => t.isTodayTask && t.status !== 'done').length;
  const urgentCount = tasks.filter(t => {
    const s = getDeadlineStatus(t.dueDate);
    return t.status !== 'done' && (s === 'overdue' || s === 'today');
  }).length;

  const navItems = [
    { id: 'tasks' as View, label: 'タスク一覧', icon: LayoutDashboard },
    { id: 'today' as View, label: 'Today', icon: Sun, badge: todayCount },
    { id: 'deadline' as View, label: '期限管理', icon: AlertTriangle, badge: urgentCount, badgeRed: true },
    { id: 'calendar' as View, label: 'カレンダー', icon: Calendar },
    { id: 'categories' as View, label: 'カテゴリ管理', icon: Tags },
  ];

  const sidebarContent = (
    <div className="flex flex-col h-full bg-gray-950 dark:bg-gray-950 text-white">
      {/* Logo */}
      <div className="flex items-center justify-between px-5 py-5 border-b border-gray-800">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-blue-600 rounded-xl flex items-center justify-center text-lg font-bold">T</div>
          <span className="font-bold text-lg tracking-tight text-white">TaskFlow</span>
        </div>
        <button
          onClick={onMobileClose}
          className="lg:hidden text-gray-400 hover:text-white transition-colors"
        >
          <X size={20} />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map(item => {
          const Icon = item.icon;
          const isActive = view === item.id;
          return (
            <button
              key={item.id}
              onClick={() => { onViewChange(item.id); onMobileClose(); }}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/25'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
            >
              <Icon size={18} />
              <span className="flex-1 text-left">{item.label}</span>
              {item.badge !== undefined && item.badge > 0 && (
                <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold ${
                  item.badgeRed ? 'bg-red-500 text-white' : 'bg-blue-500 text-white'
                }`}>
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}

        {/* Category section */}
        <div className="pt-4 pb-1">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-3 mb-2">カテゴリ</p>
          <button
            onClick={() => onCategoryFilter('')}
            className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition-all ${
              activeCategoryFilter === ''
                ? 'text-white bg-gray-800'
                : 'text-gray-400 hover:text-white hover:bg-gray-800/60'
            }`}
          >
            <span className="w-3 h-3 rounded-full bg-gray-500" />
            <span className="flex-1 text-left">すべて</span>
            <span className="text-xs text-gray-500">{tasks.filter(t => t.status !== 'done').length}</span>
          </button>
          {categories.map(cat => {
            const count = tasks.filter(t => t.categoryId === cat.id && t.status !== 'done').length;
            const isActive = activeCategoryFilter === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => { onCategoryFilter(cat.id); onViewChange('tasks'); onMobileClose(); }}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition-all ${
                  isActive
                    ? 'text-white bg-gray-800'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800/60'
                }`}
              >
                <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: cat.color }} />
                <span className="flex-1 text-left truncate">{cat.name}</span>
                {count > 0 && <span className="text-xs text-gray-500">{count}</span>}
              </button>
            );
          })}
        </div>
      </nav>

      {/* Footer */}
      <div className="px-3 py-4 border-t border-gray-800 space-y-1">
        <button
          onClick={onToggleDark}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-gray-400 hover:text-white hover:bg-gray-800 transition-all"
        >
          {darkMode ? <Sun size={18} /> : <Moon size={18} />}
          <span>{darkMode ? 'ライトモード' : 'ダークモード'}</span>
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <div className="hidden lg:flex w-60 flex-shrink-0 h-full">
        {sidebarContent}
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-black/50" onClick={onMobileClose} />
          <div className="relative w-64 h-full">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
};

export default Sidebar;
