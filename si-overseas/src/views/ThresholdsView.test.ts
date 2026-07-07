import { flushPromises, mount } from '@vue/test-utils';
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
    expect(text).not.toContain('Device photo count');
    expect(text).not.toContain('Glucose comparison group count');
    expect(text).not.toContain('Qualified comparison group count');
  });

  it('shows a success modal after saving valid changes', async () => {
    const wrapper = mount(ThresholdsView);

    await wrapper.find('#threshold-lowMinHours').setValue('5');
    await wrapper.find('button.btn-primary').trigger('click');

    // Confirm inside modal
    await wrapper.find('.threshold-modal-actions button.btn-primary').trigger('click');

    expect(wrapper.find('.modal-overlay').exists()).toBe(true);
    expect(wrapper.find('[role="alertdialog"]').text()).toContain('Settings saved');
  });

  it('shows glucose thresholds in mg/dL while saving mmol/L rule values', async () => {
    const store = useDemoStore();
    store.activeThresholdProfile.value.display = { glucoseUnit: 'mg/dL' };
    const wrapper = mount(ThresholdsView);

    expect(wrapper.find('label[for="threshold-lowBelowMmol"]').text()).toContain('mg/dL');
    expect((wrapper.find('#threshold-lowBelowMmol').element as HTMLInputElement).value).toBe('50.4');

    await wrapper.find('#threshold-lowBelowMmol').setValue('54');
    await wrapper.find('button.btn-primary').trigger('click');
    await wrapper.find('.threshold-modal-actions button.btn-primary').trigger('click');

    expect(store.activeThresholdProfile.value.rules.inaccuracy.lowPersist.belowMmol).toBe(3);
  });

  it('waits for Save Changes before persisting the glucose unit preference', async () => {
    const store = useDemoStore();
    const wrapper = mount(ThresholdsView);

    await wrapper.findAll('.unit-segment')[1].trigger('click');

    expect(store.activeThresholdProfile.value.display?.glucoseUnit).toBe('mmol/L');
    expect(wrapper.find('label[for="threshold-lowBelowMmol"]').text()).toContain('mg/dL');
    expect(wrapper.find('button.btn-primary').attributes('disabled')).toBeUndefined();

    await wrapper.find('button.btn-primary').trigger('click');
    await wrapper.find('.threshold-modal-actions button.btn-primary').trigger('click');

    expect(store.activeThresholdProfile.value.display?.glucoseUnit).toBe('mg/dL');
    expect(store.activeThresholdProfile.value.rules.inaccuracy.lowPersist.belowMmol).toBe(2.8);
  });

  it('opens a reset confirmation modal before resetting values', async () => {
    const wrapper = mount(ThresholdsView);

    await wrapper.find('#threshold-lowMinHours').setValue('5');
    await wrapper.find('button.btn-reset').trigger('click');

    expect(wrapper.find('.modal-overlay').exists()).toBe(true);
    expect(wrapper.find('[role="dialog"]').text()).toContain('Reset condition settings?');
    expect((wrapper.find('#threshold-lowMinHours').element as HTMLInputElement).value).toBe('5');
  });

  it('opens version history drawer and displays structure', async () => {
    const wrapper = mount(ThresholdsView);

    await wrapper.find('button.btn-history').trigger('click');

    expect(wrapper.find('.drawer-overlay').exists()).toBe(true);
    expect(wrapper.find('.drawer h3').text()).toBe('Version History');
  });

  it('labels the historical version removal action as delete', async () => {
    const store = useDemoStore();
    await store.saveThresholdProfileRemote({
      rules: store.activeThresholdProfile.value.rules,
    }, 'Historical version');
    await store.saveThresholdProfileRemote({
      rules: store.activeThresholdProfile.value.rules,
    }, 'Current version');

    const wrapper = mount(ThresholdsView);
    await wrapper.find('button.btn-history').trigger('click');
    await wrapper.vm.$nextTick();

    expect(wrapper.find('.history-card-actions .btn-danger').text()).toBe('Delete');
    expect(wrapper.text()).not.toContain('Hide');
  });

  it('confirms before deleting a historical threshold version', async () => {
    const store = useDemoStore();
    await store.saveThresholdProfileRemote({
      rules: store.activeThresholdProfile.value.rules,
    }, 'Historical version');
    await store.saveThresholdProfileRemote({
      rules: store.activeThresholdProfile.value.rules,
    }, 'Current version');

    const wrapper = mount(ThresholdsView);
    await wrapper.find('button.btn-history').trigger('click');
    await wrapper.vm.$nextTick();

    await wrapper.find('.history-card-actions .btn-danger').trigger('click');

    expect(wrapper.find('[role="dialog"]').text()).toContain('Delete historical version?');
    expect(wrapper.text()).toContain('Historical version');

    await wrapper.find('[data-test="threshold-delete-confirm"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('Historical version');
  });

  it('shows field-level errors without opening a modal for out-of-range values', async () => {
    const wrapper = mount(ThresholdsView);

    await wrapper.find('#threshold-lowMinHours').setValue('99');
    await wrapper.find('button.btn-primary').trigger('click');

    expect(wrapper.find('.modal-overlay').exists()).toBe(false);
    expect(wrapper.find('#threshold-lowMinHours').classes()).toContain('is-invalid');
    expect(wrapper.find('.field-message.is-error').text()).toContain('Enter a value from 1 to 24.');
  });

});
