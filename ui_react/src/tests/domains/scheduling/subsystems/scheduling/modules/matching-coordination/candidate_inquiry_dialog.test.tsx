import { fireEvent, render, screen } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CandidateInquiryDialog } from '../../../../../../../components/CandidateInquiryDialog';

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '');
    this.querySelector('button')?.focus();
  };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
});

function setup(busy = false) {
  const onClose = vi.fn();
  const view = render(<CandidateInquiryDialog title="訂單共用資訊" busy={busy} onClose={onClose}>
    <button type="button">抽屜內操作</button>
  </CandidateInquiryDialog>);
  const dialog = screen.getByRole('dialog', { name: '訂單共用資訊' });
  vi.spyOn(dialog, 'getBoundingClientRect').mockReturnValue({
    x: 360, y: 0, left: 360, right: 1440, top: 0, bottom: 1000, width: 1080, height: 1000, toJSON: () => ({}),
  });
  return { ...view, dialog, onClose };
}

const outside = { pointerId: 1, button: 0, clientX: 100, clientY: 300 };
const inside = { ...outside, clientX: 600 };

it('requests the existing close flow after pressing and releasing on the backdrop', () => {
  const { dialog, onClose } = setup();
  fireEvent.pointerDown(dialog, outside);
  fireEvent.pointerUp(dialog, outside);
  fireEvent.click(dialog, outside);
  expect(onClose).toHaveBeenCalledTimes(1);
  // The parent retains authority to keep the drawer open for unsaved changes.
  expect(dialog).toHaveAttribute('open');
});

it.each([
  ['inside blank space', inside, inside],
  ['dragging from content to backdrop', inside, outside],
  ['dragging from backdrop to content', outside, inside],
  ['a secondary mouse button', { ...outside, button: 2 }, { ...outside, button: 2 }],
  ['a different pointer', outside, { ...outside, pointerId: 2 }],
])('keeps the drawer open when %s', (_name, down, up) => {
  const { dialog, onClose } = setup();
  fireEvent.pointerDown(dialog, down);
  fireEvent.pointerUp(dialog, up);
  fireEvent.click(dialog, up);
  expect(onClose).not.toHaveBeenCalled();
});

it('does not treat child controls or a cancelled gesture as backdrop clicks', () => {
  const { dialog, onClose } = setup();
  const control = screen.getByRole('button', { name: '抽屜內操作' });
  fireEvent.pointerDown(control, outside);
  fireEvent.pointerUp(control, outside);
  fireEvent.click(control, outside);
  fireEvent.pointerDown(dialog, outside);
  fireEvent.pointerCancel(dialog, outside);
  fireEvent.pointerUp(dialog, outside);
  fireEvent.click(dialog, outside);
  expect(onClose).not.toHaveBeenCalled();
});

it('prevents backdrop and Escape dismissal while an operation is busy', () => {
  const { dialog, onClose } = setup(true);
  fireEvent.pointerDown(dialog, outside);
  fireEvent.pointerUp(dialog, outside);
  fireEvent.click(dialog, outside);
  fireEvent(dialog, new Event('cancel', { cancelable: true }));
  expect(onClose).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: '關閉' })).toBeDisabled();
});

it('checks the current busy state even when an operation starts during the gesture', () => {
  const { dialog, onClose, rerender } = setup();
  fireEvent.pointerDown(dialog, outside);
  rerender(<CandidateInquiryDialog title="訂單共用資訊" busy onClose={onClose}>內容</CandidateInquiryDialog>);
  fireEvent.pointerUp(dialog, outside);
  fireEvent.click(dialog, outside);
  expect(onClose).not.toHaveBeenCalled();
});

it('restores the opener focus when unmounting under StrictMode', () => {
  const opener = document.createElement('button');
  document.body.append(opener);
  opener.focus();
  const { unmount } = render(<StrictMode><CandidateInquiryDialog title="新增候選月嫂" onClose={vi.fn()}>內容</CandidateInquiryDialog></StrictMode>);
  expect(screen.getByRole('button', { name: '關閉' })).toHaveFocus();
  unmount();
  expect(opener).toHaveFocus();
  opener.remove();
});
