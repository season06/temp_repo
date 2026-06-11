import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

import { PanelModule } from 'primeng/panel';
import { DividerModule } from 'primeng/divider';
import { MessageModule } from 'primeng/message';

type FabSeverity = 'success' | 'warn' | 'error' | 'info' | 'secondary' | 'contrast';

interface Fab {
  name: string;
  status: 'majority' | 'minority' | 'failed';
}

interface DiffValueGroup {
  value: string;
  fabs: Fab[];
}

interface DiffColumn {
  columnName: string;
  groups: DiffValueGroup[];
}

@Component({
  selector: 'app-diff-view',
  standalone: true,
  imports: [CommonModule, PanelModule, DividerModule, MessageModule],
  templateUrl: './diff-view.component.html',
  styleUrl: './diff-view.component.scss',
})
export class PanelToggleableDemo {
  readonly totalFabCount = 12;

  readonly failedFabs: Fab[] = [
    { name: 'F21', status: 'failed' },
    { name: 'APOD', status: 'failed' },
  ];

  readonly diffColumns: DiffColumn[] = [
    {
      columnName: 'CPNT_ID',
      groups: [
        {
          value: 'CPN-00871',
          fabs: [
            { name: 'F12A', status: 'majority' },
            { name: 'F12B', status: 'majority' },
            { name: 'F14A', status: 'majority' },
            { name: 'F14B', status: 'majority' },
            { name: 'F15A', status: 'majority' },
            { name: 'F15B', status: 'majority' },
            { name: 'F16', status: 'majority' },
            { name: 'F18A', status: 'majority' },
            { name: 'F18B', status: 'majority' },
            { name: 'F22', status: 'majority' },
            { name: 'SOIC', status: 'majority' },
          ],
        },
        {
          value: 'CPN-00872',
          fabs: [{ name: 'F23', status: 'minority' }],
        },
      ],
    },
    {
      columnName: 'ENDPOINT_URL',
      groups: [
        {
          value: 'http://isop-f12a.tsmc.intra/...',
          fabs: [{ name: 'F12A', status: 'minority' }],
        },
        {
          value: 'http://isop-f12b.tsmc.intra/...',
          fabs: [{ name: 'F12B', status: 'minority' }],
        },
        {
          value: 'http://isop-f14a.tsmc.intra/...',
          fabs: [{ name: 'F14A', status: 'minority' }],
        },
        {
          value: 'http://isop-f14b.tsmc.intra/...',
          fabs: [{ name: 'F14B', status: 'minority' }],
        },
        {
          value: 'http://isop-f15a.tsmc.intra/...',
          fabs: [{ name: 'F15A', status: 'minority' }],
        },
      ],
    },
  ];

  get distinctColumnCount(): number {
    return this.diffColumns.length;
  }

  getGroupCount(group: DiffValueGroup): string {
    return `${group.fabs.length}/${this.totalFabCount}`;
  }

  getDistinctValueCount(column: DiffColumn): number {
    return column.groups.length;
  }

  getFabSeverity(fab: Fab): FabSeverity {
    switch (fab.status) {
      case 'majority':
        return 'success';
      case 'minority':
        return 'warn';
      case 'failed':
        return 'error';
      default:
        return 'secondary';
    }
  }
}
