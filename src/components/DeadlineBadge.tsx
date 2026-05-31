import React from 'react';
import { DeadlineStatus } from '../types';
import { formatDeadlineBadge, getDeadlineBadgeClass } from '../utils/deadlineUtils';

interface DeadlineBadgeProps {
  dueDate?: string;
  status: DeadlineStatus;
}

const DeadlineBadge: React.FC<DeadlineBadgeProps> = ({ dueDate, status }) => {
  if (!dueDate || status === 'ok') return null;
  const label = formatDeadlineBadge(dueDate);
  if (!label) return null;

  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${getDeadlineBadgeClass(status)}`}>
      {label}
    </span>
  );
};

export default DeadlineBadge;
