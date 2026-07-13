import { mount } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import { useDemoStore } from '@/composables/useDemoStore';
import ThresholdsView from './ThresholdsView.vue';

describe('ThresholdsView', () => {
  afterEach(() => {
    useDemoStore().resetDemoState();
  });

  it('only renders configurable condition fields without source metadata', () => {
    const wrapper = mount(ThresholdsView);
    const text = wrapper.text();

    expect(text).not.toContain('System-supplied fields');
    expect(text).not.toContain('Device status');
    expect(text).not.toContain('App home screenshot required');
    expect(text).not.toContain('Dealer');
    expect(text).not.toContain('CGM');
    expect(text).not.toContain('BGM');
    expect(text).not.toContain('Required');
    expect(text).not.toContain('Optional');
    expect(text).not.toContain('Customizable');
  });

  it('shows a success modal after saving valid changes', async () => {
    const wrapper = mount(ThresholdsView);

    await wrapper.find('#threshold-lowMinHours').setValue('5');
    await wrapper.find('button.btn-primary').trigger('click');

    expect(wrapper.find('.modal-overlay').exists()).toBe(true);
    expect(wrapper.find('[role="alertdialog"]').text()).toContain('Settings saved');
  });

  it('opens a reset confirmation modal before resetting values', async () => {
    const wrapper = mount(ThresholdsView);

    await wrapper.find('#threshold-lowMinHours').setValue('5');
    await wrapper.find('button.btn-secondary').trigger('click');

    expect(wrapper.find('.modal-overlay').exists()).toBe(true);
    expect(wrapper.find('[role="dialog"]').text()).toContain('Reset condition settings?');
    expect((wrapper.find('#threshold-lowMinHours').element as HTMLInputElement).value).toBe('5');
  });

  it('shows field-level errors without opening a modal for out-of-range values', async () => {
    const wrapper = mount(ThresholdsView);

    await wrapper.find('#threshold-lowMinHours').setValue('99');
    await wrapper.find('button.btn-primary').trigger('click');

    expect(wrapper.find('.modal-overlay').exists()).toBe(false);
    expect(wrapper.find('#threshold-lowMinHours').classes()).toContain('is-invalid');
    expect(wrapper.find('.field-message.is-error').text()).toContain('Please enter a value between 1 and 24.');
  });

});
