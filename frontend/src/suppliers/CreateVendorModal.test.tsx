import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { CreateVendorModal } from './CreateVendorModal';

const createVendor = vi.fn();

vi.mock('./api', () => ({
  useVendorsApi: () => ({ createVendor }),
}));

describe('CreateVendorModal', () => {
  beforeEach(() => {
    createVendor.mockReset().mockResolvedValue({ id: 'ven-1' });
  });

  it('requires a contact email once a contact name is typed', async () => {
    await renderWithProviders(
      <CreateVendorModal onClose={() => {}} onCreated={() => {}} />,
      { route: '/suppliers' },
    );

    const email = screen.getByLabelText('E-Mail des Ansprechpartners');
    expect(email).not.toBeRequired(); // optional while no contact is being added

    await userEvent.type(screen.getByLabelText('Name des Ansprechpartners'), 'Bernd Klose');
    expect(email).toBeRequired(); // a named contact must be reachable
  });

  it('submits without a contact when neither field is filled', async () => {
    await renderWithProviders(
      <CreateVendorModal onClose={() => {}} onCreated={() => {}} />,
      { route: '/suppliers' },
    );

    await userEvent.type(screen.getByLabelText('Firmenname'), 'Galvanik Süd');
    await userEvent.click(screen.getByRole('button', { name: 'Anlegen' }));

    expect(createVendor).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Galvanik Süd' }),
    );
    expect(createVendor.mock.calls[0][0].primary_contact).toBeUndefined();
  });
});
