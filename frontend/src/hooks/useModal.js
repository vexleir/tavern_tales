import { useContext } from 'react';
import ModalContext from '../contexts/ModalContext';

export default function useModal() {
  const ctx = useContext(ModalContext);
  if (!ctx) throw new Error('useModal must be used inside ModalProvider');
  return ctx;
}
