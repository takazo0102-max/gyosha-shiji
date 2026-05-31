import React, { useState } from 'react';
import { Plus, Edit2, Trash2, Check, X } from 'lucide-react';
import { Category } from '../types';
import ColorPicker from './ColorPicker';

interface CategoryManagerProps {
  categories: Category[];
  onAdd: (name: string, color: string) => void;
  onUpdate: (id: string, updates: Partial<Omit<Category, 'id'>>) => void;
  onDelete: (id: string) => void;
  taskCountByCategory: Record<string, number>;
}

const CategoryManager: React.FC<CategoryManagerProps> = ({
  categories, onAdd, onUpdate, onDelete, taskCountByCategory,
}) => {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editColor, setEditColor] = useState('#3B82F6');
  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState('#3B82F6');
  const [showNew, setShowNew] = useState(false);
  const [showColorFor, setShowColorFor] = useState<string | null>(null);

  const startEdit = (cat: Category) => {
    setEditingId(cat.id);
    setEditName(cat.name);
    setEditColor(cat.color);
    setShowColorFor(null);
  };

  const confirmEdit = () => {
    if (editingId && editName.trim()) {
      onUpdate(editingId, { name: editName.trim(), color: editColor });
    }
    setEditingId(null);
    setShowColorFor(null);
  };

  const confirmAdd = () => {
    if (newName.trim()) {
      onAdd(newName.trim(), newColor);
      setNewName('');
      setNewColor('#3B82F6');
      setShowNew(false);
    }
  };

  return (
    <div className="p-6 max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white">カテゴリ管理</h2>
        <button
          onClick={() => { setShowNew(true); setShowColorFor('new'); }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} />
          新規カテゴリ
        </button>
      </div>

      {showNew && (
        <div className="mb-4 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-xl border border-blue-200 dark:border-blue-800">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-4 h-4 rounded-full flex-shrink-0" style={{ backgroundColor: newColor }} />
            <input
              autoFocus
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') confirmAdd(); if (e.key === 'Escape') setShowNew(false); }}
              placeholder="カテゴリ名"
              className="flex-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button onClick={confirmAdd} className="text-green-600 hover:text-green-700 dark:text-green-400">
              <Check size={18} />
            </button>
            <button onClick={() => setShowNew(false)} className="text-gray-400 hover:text-gray-600">
              <X size={18} />
            </button>
          </div>
          <ColorPicker value={newColor} onChange={setNewColor} />
        </div>
      )}

      <div className="space-y-2">
        {categories.map(cat => (
          <div key={cat.id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            {editingId === cat.id ? (
              <div className="p-4">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-4 h-4 rounded-full flex-shrink-0" style={{ backgroundColor: editColor }} />
                  <input
                    autoFocus
                    value={editName}
                    onChange={e => setEditName(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') confirmEdit(); if (e.key === 'Escape') setEditingId(null); }}
                    className="flex-1 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-1.5 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <button onClick={confirmEdit} className="text-green-600 hover:text-green-700 dark:text-green-400">
                    <Check size={18} />
                  </button>
                  <button onClick={() => setEditingId(null)} className="text-gray-400 hover:text-gray-600">
                    <X size={18} />
                  </button>
                </div>
                <ColorPicker value={editColor} onChange={setEditColor} />
              </div>
            ) : (
              <div className="flex items-center gap-3 px-4 py-3">
                <div className="w-3 h-8 rounded-full flex-shrink-0" style={{ backgroundColor: cat.color }} />
                <span className="flex-1 font-medium text-gray-900 dark:text-white">{cat.name}</span>
                <span className="text-xs text-gray-500 dark:text-gray-400 mr-2">
                  {taskCountByCategory[cat.id] ?? 0}件
                </span>
                <button
                  onClick={() => startEdit(cat)}
                  className="p-1.5 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                >
                  <Edit2 size={15} />
                </button>
                <button
                  onClick={() => onDelete(cat.id)}
                  className="p-1.5 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {categories.length === 0 && !showNew && (
        <div className="text-center py-12 text-gray-400 dark:text-gray-500">
          <p>カテゴリがありません</p>
          <p className="text-sm mt-1">「新規カテゴリ」ボタンで作成してください</p>
        </div>
      )}
    </div>
  );
};

export default CategoryManager;
