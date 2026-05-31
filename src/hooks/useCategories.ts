import { useState, useCallback } from 'react';
import { Category } from '../types';
import { loadCategories, saveCategories } from '../utils/storage';

const generateId = () => `cat-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

export const useCategories = () => {
  const [categories, setCategories] = useState<Category[]>(() => loadCategories());

  const addCategory = useCallback((name: string, color: string) => {
    const newCat: Category = { id: generateId(), name, color };
    setCategories(prev => {
      const updated = [...prev, newCat];
      saveCategories(updated);
      return updated;
    });
    return newCat.id;
  }, []);

  const updateCategory = useCallback((id: string, updates: Partial<Omit<Category, 'id'>>) => {
    setCategories(prev => {
      const updated = prev.map(c => c.id === id ? { ...c, ...updates } : c);
      saveCategories(updated);
      return updated;
    });
  }, []);

  const deleteCategory = useCallback((id: string) => {
    setCategories(prev => {
      const updated = prev.filter(c => c.id !== id);
      saveCategories(updated);
      return updated;
    });
  }, []);

  const getCategoryById = useCallback((id: string): Category | undefined => {
    return categories.find(c => c.id === id);
  }, [categories]);

  return { categories, addCategory, updateCategory, deleteCategory, getCategoryById };
};
